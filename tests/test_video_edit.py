"""Integration checks for frame-based editing; requires ffmpeg and ffprobe."""
import json
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.video.edit_scene import assemble_timeline
from scripts.video.assemble_scene import assemble_clips


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg/ffprobe required')
class VideoEditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = ROOT / '.work' / ('video-edit-test-' + uuid.uuid4().hex)
        cls.folder.mkdir(parents=True)
        for color, frequency in [('red', 440), ('blue', 880)]:
            subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-n', '-f', 'lavfi',
                            '-i', f'color=c={color}:size=224x128:rate=24:duration=2',
                            '-f', 'lavfi', '-i', f'sine=frequency={frequency}:sample_rate=48000:duration=2',
                            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                            str(cls.folder / f'{color}.mp4')], check=True)

    def timeline(self, name, shots):
        path = self.folder / f'{name}.json'
        path.write_text(json.dumps({'version': 1, 'shots': shots}), encoding='utf-8')
        return path

    def test_short_shots_preserve_frame_count_order_and_audio(self):
        edl = self.timeline('short', [
            {'id': 'first', 'file': 'red.mp4', 'start_frame': 10, 'end_frame': 16},
            {'id': 'middle', 'file': 'blue.mp4', 'start_frame': 8, 'end_frame': 20,
             'crop': [14, 10, 112, 64], 'audio_gain': .5},
            {'id': 'last', 'file': 'red.mp4', 'start_frame': 20, 'end_frame': 23}])
        output = self.folder / 'short.mp4'
        report = assemble_timeline(edl, output)
        self.assertEqual(report['frames'], 21)
        self.assertEqual([s['timeline_start_frame'] for s in report['shots']], [0, 6, 18])
        audio = next(s for s in report['probe']['streams'] if s['codec_type'] == 'audio')
        self.assertEqual((audio['channels'], audio['sample_rate']), (2, '48000'))
        pixels = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(output),
                                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
        frame_bytes = 224 * 128 * 3
        self.assertEqual(len(pixels), 21 * frame_bytes)
        for frame in range(21):
            r, g, b = pixels[frame * frame_bytes:frame * frame_bytes + 3]
            self.assertGreater(b if 6 <= frame < 18 else r, 220)
            self.assertLess(r if 6 <= frame < 18 else b, 20)
        self.assertEqual(json.loads(output.with_suffix('.assembly.json').read_text()), report)

    def test_saved_paths_resolve_from_record_after_relocation(self):
        edl = self.timeline('portable', [{'file': 'red.mp4', 'start_frame': 0, 'end_frame': 24}])
        output = self.folder / 'nested' / 'portable.mp4'
        report = assemble_timeline(edl, output)
        self.assertEqual(report['path_base'], '.')
        self.assertEqual(report['shots'][0]['file'], '../red.mp4')
        self.assertEqual(report['edit_list'], '../portable.json')
        self.assertEqual(report['output'], 'portable.mp4')
        self.assertEqual(report['probe']['format']['filename'], 'portable.mp4')
        moved = self.folder.parent / ('relocated-' + uuid.uuid4().hex)
        shutil.copytree(self.folder, moved)
        record_folder = moved / 'nested'
        self.assertTrue((record_folder / report['shots'][0]['file']).is_file())
        self.assertTrue((record_folder / report['edit_list']).is_file())
        self.assertTrue((record_folder / report['output']).is_file())
        self.assertNotIn(str(self.folder.resolve()), json.dumps(report))

    def test_simple_assembly_saves_relative_input_and_output_paths(self):
        report = assemble_clips([self.folder / 'red.mp4', self.folder / 'blue.mp4'],
                                self.folder / 'nested' / 'joined.mp4')
        self.assertEqual([clip['file'] for clip in report['clips']], ['../red.mp4', '../blue.mp4'])
        self.assertEqual(report['output'], 'joined.mp4')
        self.assertEqual(report['clips'][0]['probe']['format']['filename'], '../red.mp4')
        self.assertNotIn(str(self.folder.resolve()), json.dumps(report))

    def test_invalid_range_does_not_create_output(self):
        edl = self.timeline('bad-range', [{'file': 'red.mp4', 'start_frame': 40, 'end_frame': 49}])
        output = self.folder / 'bad-range.mp4'
        with self.assertRaises(ValueError):
            assemble_timeline(edl, output)
        self.assertFalse(output.exists())

    def test_bad_crop_is_rejected(self):
        edl = self.timeline('bad-crop', [{'file': 'red.mp4', 'start_frame': 0, 'end_frame': 6,
                                         'crop': [200, 0, 112, 64]}])
        with self.assertRaises(ValueError):
            assemble_timeline(edl, self.folder / 'bad-crop.mp4')

    def test_existing_record_is_preserved(self):
        edl = self.timeline('protected', [{'file': 'red.mp4', 'start_frame': 0, 'end_frame': 6}])
        output = self.folder / 'protected.mp4'
        record = output.with_suffix('.assembly.json')
        record.write_text('existing record')
        with self.assertRaises(FileExistsError):
            assemble_timeline(edl, output)
        self.assertEqual(record.read_text(), 'existing record')
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
