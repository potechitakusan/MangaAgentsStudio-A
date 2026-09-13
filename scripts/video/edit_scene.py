"""Assemble a 24-fps edit list, including short inserts, with an audit record.

JSON: {"version": 1, "shots": [{"id": "F01", "file": "clip.mp4",
"start_frame": 0, "end_frame": 24}]}. End frames are exclusive. Paths are
relative to the JSON file. Inputs require audio and matching dimensions.
Optional crop is [x, y, width, height]; audio_gain defaults to 1.0.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

if __package__:
    from .paths import relative_path, portable_command, portable_probe
else:
    from paths import relative_path, portable_command, portable_probe


def probe(filename, ffprobe):
    return json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-show_streams',
                                               '-show_format', '-of', 'json', str(filename)]))


def assemble_timeline(edit_list, output, *, ffmpeg='ffmpeg', ffprobe='ffprobe'):
    """Render a timeline JSON to MP4 and return its .assembly.json report."""
    edit_list, output = Path(edit_list), Path(output)
    record = output.with_suffix('.assembly.json')
    record_base = record.parent
    edit_list_relative = relative_path(edit_list, record_base)
    if output.exists() or record.exists():
        raise FileExistsError('Output or assembly record exists; choose a new version.')
    data = json.loads(edit_list.read_text(encoding='utf-8-sig'))
    shots = data.get('shots', [])
    if data.get('version') != 1 or not shots:
        raise ValueError('Expected version 1 and a nonempty shots list.')
    fps, total, inputs, filters, entries, geometry = 24, 0, [], [], [], None
    info_cache = {}
    for i, shot in enumerate(shots):
        source = (edit_list.parent / shot['file']).resolve()
        if source not in info_cache:
            info_cache[source] = probe(source, ffprobe)
        info = info_cache[source]
        video = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
        audio = next((s for s in info['streams'] if s['codec_type'] == 'audio'), None)
        if not video or not audio:
            raise ValueError(f'Video and audio required: {source}')
        if Fraction(video['r_frame_rate']) != fps or Fraction(video['avg_frame_rate']) != fps:
            raise ValueError(f'Normalize input to constant 24 fps first: {source}')
        size = (video['width'], video['height'])
        if geometry is None:
            geometry = size
        if size != geometry:
            raise ValueError('Input dimensions must match.')
        available = int(video['nb_frames'])
        start, end = shot['start_frame'], shot['end_frame']
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= available:
            raise ValueError(f'Invalid frame range for {shot.get("id", i)}: {start}:{end}, available {available}')
        if available > 241:
            raise ValueError('Use short source clips, at most approximately 10 seconds.')
        duration = (end - start) / fps
        vfilter = f'[{i}:v:0]trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS'
        crop = shot.get('crop')
        if crop is not None:
            if len(crop) != 4 or any(type(x) is not int or x < 0 or x % 2 for x in crop):
                raise ValueError('crop must contain four nonnegative even integers.')
            x, y, w, h = crop
            if not w or not h or x+w > size[0] or y+h > size[1] or w*size[1] != h*size[0]:
                raise ValueError('crop must fit the frame and preserve its aspect ratio.')
            vfilter += f',crop={w}:{h}:{x}:{y},scale={size[0]}:{size[1]}:flags=lanczos'
        filters.append(vfilter + f',setsar=1[v{i}]')
        gain = shot.get('audio_gain', 1.0)
        if type(gain) not in (int, float) or not math.isfinite(gain) or not 0 <= gain <= 4:
            raise ValueError('audio_gain must be between 0 and 4.')
        # Five-ms fades remove sample discontinuities without changing shot length.
        filters.append(f'[{i}:a:0]atrim=start={start/fps}:end={end/fps},asetpts=PTS-STARTPTS,'
                       f'aresample=48000,aformat=channel_layouts=stereo,apad=whole_dur={duration},'
                       f'atrim=duration={duration},volume={gain},afade=t=in:d=0.005,'
                       f'afade=t=out:st={max(0, duration-.005)}:d=0.005[a{i}]')
        inputs += ['-i', str(source)]
        entries.append({**shot, 'file': relative_path(source, record_base), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                        'timeline_start_frame': total, 'frames': end-start, 'seconds': duration})
        total += end-start
    streams = ''.join(f'[v{i}][a{i}]' for i in range(len(shots)))
    filters.append(f'{streams}concat=n={len(shots)}:v=1:a=1[v][a]')
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [ffmpeg, '-hide_banner', '-loglevel', 'warning', '-nostdin', '-n', *inputs,
               '-filter_complex', ';'.join(filters), '-map', '[v]', '-map', '[a]',
               '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
               '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(output)]
    subprocess.run(command, check=True)
    info = probe(output, ffprobe)
    v = next(s for s in info['streams'] if s['codec_type'] == 'video')
    if int(v['nb_frames']) != total:
        raise RuntimeError(f'Output frame count differs: {v["nb_frames"]} != {total}')
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'mode': 'frame_edit_list',
              'path_base': '.', 'edit_list': edit_list_relative, 'edit_list_sha256': hashlib.sha256(edit_list.read_bytes()).hexdigest(),
              'fps': fps, 'frames': total, 'seconds': total/fps, 'shots': entries, 'command': portable_command(command, record_base),
              'output': relative_path(output, record_base), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
              'probe': portable_probe(info, record_base), 'content_review': '映像と音声の内容確認は別途必要。'}
    with record.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--edit-list', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--ffprobe', default='ffprobe')
    args = parser.parse_args()
    try:
        result = assemble_timeline(args.edit_list, args.output, ffmpeg=args.ffmpeg, ffprobe=args.ffprobe)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    print(json.dumps({'output': result['output'], 'frames': result['frames'],
                      'seconds': result['seconds'], 'shots': len(result['shots'])}))


if __name__ == '__main__':
    main()
