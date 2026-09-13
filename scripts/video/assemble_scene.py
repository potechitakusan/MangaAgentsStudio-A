"""Join short clips in order with audio, using ffmpeg; usable as CLI or Python API.

Requires Python 3.10+ and ffmpeg/ffprobe. No third-party Python packages or
ComfyUI server are needed. See docs/knowledge/video-assembly.md for examples.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from .paths import relative_path, portable_command, portable_probe
else:
    from paths import relative_path, portable_command, portable_probe


def probe(filename, ffprobe):
    result = subprocess.run([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(filename)],
                            check=True, capture_output=True, text=True, encoding='utf-8')
    return json.loads(result.stdout)


def assemble_clips(clips, output, *, trim_seconds=None, ffmpeg='ffmpeg', ffprobe='ffprobe'):
    """Write an MP4 and <stem>.assembly.json, returning the assembly report.

    ``clips`` is an ordered iterable of paths. Each input must contain video and
    audio, be 1 to 10.05 seconds long, and have matching pixel dimensions.
    ``trim_seconds`` retains at most that many seconds from each input's start;
    retained clips must still be at least one second long. Output is 24 fps,
    H.264/AAC, stereo 48 kHz. Existing output or report files are never replaced.

    Raises ValueError for unsuitable clips/settings, FileExistsError for an
    existing destination, or subprocess/OSError exceptions for tool failures.
    Media/encoding errors may leave a partial output for inspection.
    """
    clips = [Path(clip) for clip in clips]
    output = Path(output)
    report_path = output.with_suffix('.assembly.json')
    record_base = report_path.parent
    portable_clips = [relative_path(clip, record_base) for clip in clips]
    if not clips:
        raise ValueError('Provide at least one clip.')
    for destination in (output, report_path):
        if destination.exists():
            raise FileExistsError(f'Output or report already exists: {destination}; use a new versioned filename.')
    if trim_seconds is not None and not 0 < trim_seconds <= 10:
        raise ValueError('trim_seconds must be greater than zero and at most 10')
    infos = [probe(clip, ffprobe) for clip in clips]
    inputs = []
    size = None
    filters = []
    segments = []
    for index, (clip, info) in enumerate(zip(clips, infos)):
        video = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
        audio = next((s for s in info['streams'] if s['codec_type'] == 'audio'), None)
        if video is None or audio is None:
            raise ValueError(f'Expected both video and audio: {clip}')
        dimensions = (video['width'], video['height'])
        if size is None:
            size = dimensions
        if dimensions != size:
            raise ValueError('All clips must have matching dimensions; normalize explicitly before assembling.')
        duration = float(info['format']['duration'])
        if duration > 10.05:
            raise ValueError(f'Clip exceeds the requested 10-second maximum: {clip}')
        keep = min(duration, trim_seconds) if trim_seconds is not None else duration
        if keep < 1:
            raise ValueError(f'Retained clip must be at least one second long: {clip}')
        filters.append(f'[{index}:v]trim=duration={keep},setpts=PTS-STARTPTS,fps=24,setsar=1[v{index}]')
        filters.append(f'[{index}:a]atrim=duration={keep},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a{index}]')
        inputs += ['-i', str(clip)]
        segments.append({'file': portable_clips[index], 'source_seconds': duration, 'retained_seconds': keep,
                         'sha256': hashlib.sha256(clip.read_bytes()).hexdigest(), 'probe': portable_probe(info, record_base)})
    inputs_for_concat = ''.join(f'[v{i}][a{i}]' for i in range(len(clips)))
    filters.append(f'{inputs_for_concat}concat=n={len(clips)}:v=1:a=1[v][a]')
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [ffmpeg, '-hide_banner', '-loglevel', 'warning', '-nostdin', '-n', *inputs,
               '-filter_complex', ';'.join(filters), '-map', '[v]', '-map', '[a]',
               '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
               '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(output)]
    subprocess.run(command, check=True)
    final_info = probe(output, ffprobe)
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'path_base': '.',
              'clips': segments, 'command': portable_command(command, record_base),
              'output': relative_path(output, record_base), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
              'probe': portable_probe(final_info, record_base), 'content_review': '内容の通読・試聴は別途必要。'}
    with report_path.open('x', encoding='utf-8') as record:
        record.write(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clip', action='append', required=True, type=Path, help='Input clip; repeat in playback order')
    parser.add_argument('--output', required=True, type=Path, help='New output MP4 path')
    parser.add_argument('--trim-seconds', type=float, help='Optional maximum retained duration per clip')
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--ffprobe', default='ffprobe')
    args = parser.parse_args()
    try:
        report = assemble_clips(args.clip, args.output, trim_seconds=args.trim_seconds,
                                ffmpeg=args.ffmpeg, ffprobe=args.ffprobe)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    print(json.dumps({'output': str(args.output), 'seconds': report['probe']['format']['duration'],
                      'clips': len(report['clips'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
