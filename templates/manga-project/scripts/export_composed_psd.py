"""原画を保持し、コマ外を画素削除ではなくPSDマスクで隠す。

既定はPNGプレビューのみ。PSDは確認済みの依頼時だけ --write-psd。
配置用レイヤーの回転・拡大は再サンプリングするが、切り捨てない。
未加工の全画素は別の非表示グループへ格納する（スマートオブジェクトではない）。
"""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops

MAX_PIXELS=64_000_000

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()

def bounded_path(root:Path,value:str)->Path:
    path=(root/value).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('パスが指定ルート外です: '+value)
    return path

def load_source(root:Path,path:str,expected:str|None=None)->tuple[Image.Image,Path]:
    p=bounded_path(root,path)
    if expected and sha(p)!=expected:raise ValueError('原画のSHA-256が一致しません: '+path)
    with Image.open(p) as opened:
        if opened.width*opened.height>MAX_PIXELS:raise ValueError('原画が安全な画素数を超えています')
        return opened.convert('RGBA'),p

def full_affine(source:Image.Image,frame:list,affine:list)->tuple[Image.Image,tuple[int,int]]:
    """配置先の枠ではなく、変換した元画像全体を包含する矩形へ描画。"""
    if len(frame)!=4 or len(affine)!=6 or not all(math.isfinite(v) for v in frame+affine):raise ValueError('配置座標が不正です')
    if frame[2]<=frame[0] or frame[3]<=frame[1]:raise ValueError('枠は正の大きさが必要です')
    a,b,c,d,e,f=map(float,affine);det=a*e-b*d
    if abs(det)<1e-12:raise ValueError('逆変換できない行列です')
    def forward(x,y):return ((e*(x-c)-b*(y-f))/det+frame[0],(-d*(x-c)+a*(y-f))/det+frame[1])
    corners=[forward(x,y) for x,y in [(0,0),(source.width,0),(source.width,source.height),(0,source.height)]]
    left=math.floor(min(x for x,y in corners))-2;top=math.floor(min(y for x,y in corners))-2
    right=math.ceil(max(x for x,y in corners))+2;bottom=math.ceil(max(y for x,y in corners))+2
    width,height=right-left,bottom-top
    if width>30000 or height>30000 or width*height>MAX_PIXELS:raise ValueError('変換後のレイヤーが安全な大きさを超えています')
    dx,dy=left-frame[0],top-frame[1]
    matrix=(a,b,c+a*dx+b*dy,d,e,f+d*dx+e*dy)
    return source.transform((width,height),Image.Transform.AFFINE,matrix,Image.Resampling.BICUBIC,fillcolor=(0,0,0,0)),(left,top)

def panel_mask(size:tuple,offset:tuple,polygon:list)->Image.Image:
    if len(polygon)<3 or any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in polygon):raise ValueError('コマの多角形が不正です')
    mask=Image.new('L',size,0);ImageDraw.Draw(mask).polygon([(x-offset[0],y-offset[1]) for x,y in polygon],fill=255)
    if not mask.getbbox():raise ValueError('表示範囲が空です')
    return mask

def render_document(spec:dict,root:Path,make_psd:bool=False):
    if spec.get('schema_version')!=1:raise ValueError('未対応のschema_versionです')
    page=spec['page'];size=tuple(page['size'])
    if len(size)!=2 or any(type(v)!=int or v<=0 or v>30000 for v in size) or math.prod(size)>MAX_PIXELS:raise ValueError('ページ寸法が不正です')
    if page.get('mode','RGB') not in ('RGB','L'):raise ValueError('ページ色モードはRGBまたはLのみです')
    dpi=page.get('dpi',300)
    if type(dpi) not in (float,int) or not math.isfinite(dpi) or not 1<=dpi<=2400:raise ValueError('dpiは1〜2400です')
    names=['元画像（未加工・非表示）','用紙']
    for i,p in enumerate(spec.get('panels',[]),1):
        n=p.get('name',f'コマ{i:02}')
        if not isinstance(n,str) or not n.strip():raise ValueError('コマ名は空でない文字列です')
        names.extend([n+' 採用原画・未加工',n+' 配置画像（コマ外はマスク）'])
        if p.get('original_source') and p['original_source']!=p['source']:names.append(n+' NovelAI生成原画・修正前')
    names.extend(e['name'] for e in spec.get('overlays',[]))
    if len(names)!=len(set(names)) or any(not isinstance(n,str) or not n or len(n)>=256 for n in names):raise ValueError('レイヤー名が重複または不正です')
    preview=Image.new('RGBA',size,'white');psd=None;originals=None
    if make_psd:
        from psd_tools import PSDImage
        from psd_tools.api.layers import Group,PixelLayer
        psd=PSDImage.new('RGBA',size)
        originals=Group.new(psd,'元画像（未加工・非表示）');originals.visible=False
        PixelLayer.frompil(Image.new('RGBA',size,'white'),psd,'用紙')
    records=[];source_paths=set();saved_originals=set()
    def keep_original(path,expected,label):
        raw,p=load_source(root,path,expected);source_paths.add(p)
        token=(str(p),label)
        if psd is not None and token not in saved_originals:
            PixelLayer.frompil(raw,originals,label);saved_originals.add(token)
        return dict(path=p.relative_to(root).as_posix(),sha256=sha(p),rgba_sha256=hashlib.sha256(raw.tobytes()).hexdigest(),size=list(raw.size),layer_name=label)
    for index,panel in enumerate(spec.get('panels',[]),1):
        name=panel.get('name',f'コマ{index:02}');raw,p=load_source(root,panel['source'],panel.get('source_sha256'));source_paths.add(p)
        selected=keep_original(panel['source'],panel.get('source_sha256'),name+' 採用原画・未加工')
        generated=None
        if panel.get('original_source') and panel['original_source']!=panel['source']:
            generated=keep_original(panel['original_source'],panel.get('original_sha256'),name+' NovelAI生成原画・修正前')
        if panel.get('monochrome',False):
            gray=raw.convert('L');display=Image.merge('RGBA',(gray,gray,gray,raw.getchannel('A')))
        else:display=raw
        # 旧組版でalphaを使わなかった場合だけ表示を再現。保存原画は変更しない。
        if panel.get('display_opaque',False):
            display=display.copy();display.putalpha(255)
        full,offset=full_affine(display,panel['frame'],panel['inverse_affine'])
        mask=panel_mask(full.size,offset,panel['polygon']);visible=full.copy();visible.putalpha(ImageChops.multiply(full.getchannel('A'),mask));preview.alpha_composite(visible,offset)
        layer_name=name+' 配置画像（コマ外はマスク）'
        if psd is not None:
            layer=PixelLayer.frompil(full,psd,layer_name,top=offset[1],left=offset[0]);layer.create_mask(mask,top=offset[1],left=offset[0])
        records.append(dict(name=name,layer_name=layer_name,selected_original=selected,novelai_original=generated,offset=list(offset),display_size=list(full.size),full_rgba_sha256=hashlib.sha256(full.tobytes()).hexdigest(),mask_sha256=hashlib.sha256(mask.tobytes()).hexdigest(),polygon=panel['polygon'],inverse_affine=panel['inverse_affine'],frame=panel['frame'],monochrome=panel.get('monochrome',False),display_opaque=panel.get('display_opaque',False),source_pixels_cropped=False))
    overlay_records=[]
    for entry in spec.get('overlays',[]):
        im,p=load_source(root,entry['source'],entry.get('source_sha256'));source_paths.add(p)
        offset=tuple(entry.get('position',[0,0]));name=entry['name']
        if len(offset)!=2 or any(type(v)!=int for v in offset):raise ValueError('重ね画像の位置が不正です')
        if entry.get('visible',True):preview.alpha_composite(im,offset)
        if psd is not None:
            layer=PixelLayer.frompil(im,psd,name,top=offset[1],left=offset[0]);layer.visible=entry.get('visible',True)
        overlay_records.append(dict(name=name,source=p.relative_to(root).as_posix(),sha256=sha(p),size=list(im.size),position=list(offset)))
    report=dict(schema_version=1,page=page,panels=records,overlays=overlay_records,source_files=sorted(p.relative_to(root).as_posix() for p in source_paths),originals_preserved=True,crop_method_ja='配置画像は全体を保持し、ピクセルマスクで表示範囲だけを制限',transform_limit_ja='配置画像の回転・拡大はラスタライズ。元の全RGBA画素を別グループに保持し、変換行列を同梱する。スマートオブジェクトではない。',csp_readback_ja='CLIP STUDIO PAINTでの実読込は未確認')
    return preview.convert(page.get('mode','RGB')),psd,report

def verify_psd(path:Path,preview:Image.Image,report:dict)->dict:
    from psd_tools import PSDImage
    import numpy as np
    psd=PSDImage.open(path);layers={layer.name:layer for layer in psd.descendants()};original_group=layers['元画像（未加工・非表示）']
    if original_group.visible:raise AssertionError('原画グループが表示されています')
    for p in report['panels']:
        for raw in (p['selected_original'],p['novelai_original']):
            if raw is None:continue
            layer=layers[raw['layer_name']];im=layer.topil(apply_icc=False).convert('RGBA')
            assert list(im.size)==raw['size'] and hashlib.sha256(im.tobytes()).hexdigest()==raw['rgba_sha256']
        layer=layers[p['layer_name']];full=layer.topil(apply_icc=False).convert('RGBA')
        assert list(full.size)==p['display_size'] and list(layer.offset)==p['offset']
        assert hashlib.sha256(full.tobytes()).hexdigest()==p['full_rgba_sha256']
        assert layer.has_mask() and not layer.mask.disabled
        assert hashlib.sha256(layer.mask.topil().tobytes()).hexdigest()==p['mask_sha256']
    actual=psd.composite(force=True,apply_icc=False).convert(preview.mode)
    delta=np.abs(np.asarray(actual,dtype=np.int16)-np.asarray(preview,dtype=np.int16));maximum=int(delta.max());mean=float(delta.mean())
    if maximum>1:raise AssertionError(f'PSD再合成差が大きすぎます: 最大{maximum} / 平均{mean}')
    return dict(passed=True,layer_count=len(layers),original_pixel_hashes_match=True,full_display_pixel_hashes_match=True,masks_present=True,composite_max_difference=maximum,composite_mean_difference=mean,csp_readback=False)

def export(spec:dict,root:Path,base:Path,write_psd:bool=False,overwrite:bool=False)->dict:
    root=root.resolve();base=bounded_path(root,str(base));targets=[base.with_suffix('.png'),base.with_suffix('.json')]
    if write_psd:targets.append(base.with_suffix('.psd'))
    if not overwrite and any(p.exists() for p in targets):raise FileExistsError('既存出力があります。別名または --overwrite を指定してください')
    preview,psd,report=render_document(spec,root,write_psd)
    source_set={bounded_path(root,p) for p in report['source_files']}
    if source_set.intersection(targets):raise ValueError('入力原画への上書きは禁止です')
    base.parent.mkdir(parents=True,exist_ok=True);preview.save(base.with_suffix('.png'),dpi=(spec['page'].get('dpi',300),)*2)
    if write_psd:
        from psd_tools.constants import Resource
        # ライブラリ1.19.0の公開クラス名にはこの綴りが使われている。
        from psd_tools.psd.image_resources import ImageResource,ResoulutionInfo
        dpi=spec['page'].get('dpi',300)
        if not isinstance(dpi,(float,int)) or not math.isfinite(dpi) or not 1<=dpi<=2400:raise ValueError('dpiは1〜2400です')
        psd.image_resources[Resource.RESOLUTION_INFO]=ImageResource(key=Resource.RESOLUTION_INFO,data=ResoulutionInfo(horizontal=round(dpi*65536),horizontal_unit=1,width_unit=1,vertical=round(dpi*65536),vertical_unit=1,height_unit=1))
        # setterでUnicode名タグを必ず付け、旧Pascal名は互換な代替表記にする。
        for layer in psd.descendants():layer.name=layer.name
        psd.save(base.with_suffix('.psd'))
        report['verification']=verify_psd(base.with_suffix('.psd'),preview,report)
    else:report['verification']=dict(preview_only=True,psd_created=False)
    report['output_png']=str(base.with_suffix('.png').relative_to(root));report['png_sha256']=sha(base.with_suffix('.png'))
    base.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--manifest',required=True);ap.add_argument('--root',default='.');ap.add_argument('--output',required=True);ap.add_argument('--write-psd',action='store_true');ap.add_argument('--overwrite',action='store_true');args=ap.parse_args()
    root=Path(args.root).resolve();spec=json.loads(bounded_path(root,args.manifest).read_text(encoding='utf-8'))
    result=export(spec,root,Path(args.output),args.write_psd,args.overwrite);print(json.dumps(result['verification'],ensure_ascii=False))
if __name__=='__main__':main()
