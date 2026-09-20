import sys,unittest,shutil,uuid
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'templates/manga-project/scripts'))
from export_composed_psd import full_affine,render_document,export

class PreservationTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'tmp').mkdir(exist_ok=True);self.root=ROOT/'tmp'/('psd-test-'+uuid.uuid4().hex);self.root.mkdir(mode=0o777)
        im=Image.new('RGBA',(80,60));d=ImageDraw.Draw(im)
        for y in range(60):
            for x in range(80):d.point((x,y),fill=(x*3,y*4,(x+y)*2,128 if x<8 else 255))
        im.save(self.root/'original.png');edited=im.copy();ImageDraw.Draw(edited).rectangle((10,10,20,20),fill='red');edited.save(self.root/'edited.png')
        self.spec=dict(schema_version=1,page=dict(size=[64,64],mode='RGB',dpi=300),panels=[dict(name='コマ01',source='edited.png',original_source='original.png',frame=[8,8,56,56],polygon=[[8,8],[56,8],[56,56],[8,56]],inverse_affine=[1,0,10,0,1,5])],overlays=[])
    def tearDown(self):
        assert self.root.resolve().parent==(ROOT/'tmp').resolve() and self.root.name.startswith('psd-test-')
        shutil.rmtree(self.root)
    def test_full_extent(self):
        im=Image.open(self.root/'original.png');full,pos=full_affine(im,[8,8,56,56],[1,0,10,0,1,5]);self.assertEqual(full.size,(84,64));self.assertEqual(pos,(-4,1));self.assertEqual(full.getpixel((12,12)),im.getpixel((10,10)))
    def test_preview_masks_outside(self):
        im,psd,r=render_document(self.spec,self.root);self.assertIsNone(psd);self.assertEqual(im.getpixel((1,1)),(255,255,255));self.assertFalse(r['panels'][0]['source_pixels_cropped'])
    def test_roundtrip_and_toggle(self):
        from psd_tools import PSDImage
        r=export(self.spec,self.root,Path('test'),True);self.assertTrue(r['verification']['passed'])
        psd=PSDImage.open(self.root/'test.psd');layer=next(l for l in psd.descendants() if l.name.startswith('コマ01 配置'))
        before=layer.composite(viewport=layer.bbox,force=True);layer.mask.disabled=True;after=layer.composite(viewport=layer.bbox,force=True)
        self.assertGreater(sum(after.getchannel('A').tobytes()),sum(before.getchannel('A').tobytes()))
    def test_rotated_full_image(self):
        self.spec['panels'][0]['inverse_affine']=[.8,-.2,12,.2,.8,2]
        r=export(self.spec,self.root,Path('rotated'),True);self.assertTrue(r['verification']['passed']);self.assertGreater(r['panels'][0]['display_size'][0],80)
    def test_sha_mismatch(self):
        self.spec['panels'][0]['source_sha256']='0'*64
        with self.assertRaises(ValueError):render_document(self.spec,self.root)
    def test_opaque_display_keeps_original_alpha(self):
        self.spec['panels'][0].update(display_opaque=True,monochrome=True)
        r=export(self.spec,self.root,Path('opaque'),True)
        self.assertTrue(r['verification']['original_pixel_hashes_match'])
        self.assertTrue(r['panels'][0]['display_opaque'])
    def test_singular_and_size(self):
        im=Image.open(self.root/'original.png').convert('RGBA')
        with self.assertRaises(ValueError):full_affine(im,[0,0,10,10],[1,1,0,1,1,0])
        with self.assertRaises(ValueError):full_affine(im,[0,0,10,10],[.0001,0,0,0,.0001,0])
    def test_overwrite_protection(self):
        export(self.spec,self.root,Path('test'))
        with self.assertRaises(FileExistsError):export(self.spec,self.root,Path('test'))
        with self.assertRaises(ValueError):export(self.spec,self.root,Path('../outside'))
    def test_original_cannot_be_output(self):
        with self.assertRaises(ValueError):export(self.spec,self.root,Path('original'),overwrite=True)

if __name__=='__main__':unittest.main()
