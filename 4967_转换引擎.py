# SPDX-License-Identifier: MIT
"""4967：受控6×6 SVG模板的铁路图案转水管图案原型。"""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import xml.etree.ElementTree as ET

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
NS = "{" + SVG + "}"
DIRS = {"N":(-1,0),"E":(0,1),"S":(1,0),"W":(0,-1)}
OPPOSITE = {"N":"S","S":"N","E":"W","W":"E"}
KINDS = {"NS","EW","NE","NW","SE","SW"}
MAX_BYTES = 1_000_000


class ConversionError(ValueError):
    pass


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_path(value, *, existing=True):
    path = Path(os.path.abspath(value))
    for item in [path,*path.parents]:
        if item.exists() or item.is_symlink():
            info=item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info,"st_file_attributes",0)&0x400:
                raise ConversionError("拒绝符号链接或目录连接点")
    if existing and not path.is_file(): raise ConversionError("输入不存在或不是普通文件")
    if not path.parent.is_dir(): raise ConversionError("父目录必须已经存在")
    return path


def read_safe(path):
    path=safe_path(path)
    with path.open("rb") as stream: raw=stream.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES: raise ConversionError("SVG超过1,000,000字节")
    return raw


def centerline(row,col,kind):
    x,y=150+60*col,150+60*row
    if kind=="NS": return f"M {x} {y-30} L {x} {y+30}"
    if kind=="EW": return f"M {x-30} {y} L {x+30} {y}"
    start=y-30 if kind[0]=="N" else y+30
    end=x+30 if kind[1]=="E" else x-30
    return f"M {x} {start} Q {x} {y} {end} {y}"


def glyph_attributes(d,mode):
    base=dict(d=d,fill="none",stroke="black",**{"stroke-width":"6","stroke-linecap":"round","stroke-linejoin":"round"})
    if mode=="rail":
        return [base,{**base,"stroke":"white","stroke-width":"3"},{**base,"stroke-width":"10","stroke-dasharray":"2 9"}]
    return [{**base,"stroke-width":"10"},{**base,"stroke":"white","stroke-width":"6"}]


def check_protected(group):
    allowed={"g":{"id"},"rect":{"id","x","y","width","height","fill","stroke","stroke-width"},
             "line":{"id","x1","y1","x2","y2","stroke","stroke-width"},
             "text":{"id","x","y","font-family","font-size","font-weight","text-anchor","fill"}}
    numeric={"x","y","x1","y1","x2","y2","width","height","stroke-width","font-size"}
    for node in group.iter():
        tag=node.tag.removeprefix(NS)
        if node.tag!=NS+tag or tag not in allowed or set(node.attrib)-allowed[tag]:
            raise ConversionError("网格、数字或标签包含不支持的元素或属性")
        if tag!="text" and (node.text or "").strip(): raise ConversionError("非文字元素包含正文")
        if tag!="g" and len(node): raise ConversionError("基本图形或文字不可包含子元素")
        if tag=="text" and (len(node.text or "")>200 or any(ord(c)<32 or ord(c)>126 for c in (node.text or ""))):
            raise ConversionError("本模板标签仅支持200字符内可打印ASCII文字")
        if node.tail and node.tail.strip(): raise ConversionError("元素尾部包含非空文本")
        for name,value in node.attrib.items():
            if name in numeric:
                if not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?",value): raise ConversionError("坐标或线宽不是支持的非负数")
                number=float(value)
                maximum=48 if name=="font-size" else 10 if name=="stroke-width" else 600
                if not math.isfinite(number) or number>maximum or (name in {"width","height","font-size"} and number<=0):
                    raise ConversionError("坐标、尺寸或线宽越出模板范围")
            elif name in {"fill","stroke"} and value not in {"black","white","none"}: raise ConversionError("仅支持纯黑白图形")
            elif name=="font-family" and value not in {"Arial","sans-serif"}: raise ConversionError("不支持该字体")
            elif name=="font-weight" and value not in {"normal","bold"}: raise ConversionError("不支持该字重")
            elif name=="text-anchor" and value not in {"start","middle","end"}: raise ConversionError("不支持该文字锚点")


def check_template_layers(root):
    grid,numbers,labels=root[:3]
    expected=[(NS+"rect",dict(x="120",y="120",width="360",height="360",fill="white",stroke="black",**{"stroke-width":"2"}))]
    for edge in range(180,421,60):
        expected.extend([(NS+"line",dict(x1=str(edge),y1="120",x2=str(edge),y2="480",stroke="black",**{"stroke-width":"2"})),
                         (NS+"line",dict(x1="120",y1=str(edge),x2="480",y2=str(edge),stroke="black",**{"stroke-width":"2"}))])
    if [(node.tag,{k:v for k,v in node.attrib.items() if k!="id"}) for node in grid]!=expected:
        raise ConversionError("网格必须是固定位置与线宽的完整6×6网格")
    positions=[(str(150+60*c),"102") for c in range(6)]+[("100",str(158+60*r)) for r in range(6)]
    if len(numbers)!=12 or any(node.tag!=NS+"text" or (node.get("x"),node.get("y"))!=position or (node.text or "") not in "0123456" or len(node.text or "")!=1 for node,position in zip(numbers,positions)):
        raise ConversionError("数字层须包含固定位置的12个0至6数字")
    if len(labels)!=3 or any(node.tag!=NS+"text" or not (node.text or "").strip() for node in labels):
        raise ConversionError("标签层须包含三个非空文字标签")
    if root.get("data-state")=="solution":
        cells=geometry(root)
        counts=[sum(item["col"]==c for item in cells) for c in range(6)]+[sum(item["row"]==r for item in cells) for r in range(6)]
        if [int(node.text) for node in numbers]!=counts: raise ConversionError("答案行列数字与路线占用格数不一致")


def geometry(root):
    result=[]
    for cell in root.find(NS+"g[@id='tracks']"):
        row,col=int(cell.get("data-row")),int(cell.get("data-col"))
        kind=cell.get("data-kind");x,y=150+60*col,150+60*row
        endpoints=[]
        for direction in kind:
            dr,dc=DIRS[direction];endpoints.append([x+30*dc,y+30*dr])
        result.append(dict(row=row,col=col,kind=kind,d=cell[0].get("d"),endpoints=endpoints))
    return sorted(result,key=lambda item:(item["row"],item["col"]))


def check_connections(root):
    cells={(item["row"],item["col"]):set(item["kind"]) for item in geometry(root)}
    external=[];adj={key:set() for key in cells}
    for (row,col),directions in cells.items():
        for direction in directions:
            dr,dc=DIRS[direction];other=(row+dr,col+dc)
            if not 0<=other[0]<6 or not 0<=other[1]<6:
                external.append([row,col,direction])
            elif other in cells and OPPOSITE[direction] in cells[other]: adj[(row,col)].add(other)
            elif root.get("data-state")=="solution": raise ConversionError("答案路线在格内存在断口")
    if root.get("data-state")=="solution":
        visited=set();pending=[next(iter(cells))]
        while pending:
            key=pending.pop()
            if key not in visited: visited.add(key);pending.extend(adj[key]-visited)
        if len(visited)!=len(cells) or len(external)!=2: raise ConversionError("答案须为连通且恰有两个边界出入口的路线")
    return sorted(external)


def parse_svg_bytes(raw,expected_mode="rail"):
    if not isinstance(raw,bytes) or len(raw)>MAX_BYTES: raise ConversionError("SVG字节或大小不合法")
    try: text=raw.decode("utf-8",errors="strict")
    except UnicodeDecodeError as exc: raise ConversionError("SVG必须为UTF-8") from exc
    text=re.sub(r"^\ufeff?<\?xml version=['\"]1\.0['\"] encoding=['\"]utf-8['\"]\?>","",text,count=1,flags=re.I)
    if any(token in text.upper() for token in ["<!DOCTYPE","<!ENTITY","<!--","<?"]): raise ConversionError("拒绝DTD、实体、注释或处理指令")
    try: root=ET.fromstring(text)
    except ET.ParseError as exc: raise ConversionError("XML无法解析") from exc
    expected={"width":"160mm","height":"160mm","viewBox":"0 0 600 600","data-demo":"4967","data-mode":expected_mode,"data-state":root.get("data-state")}
    if root.tag!=NS+"svg" or root.attrib!=expected or expected["data-state"] not in {"puzzle","solution"}:
        raise ConversionError("仅支持带4967标记的160mm受控6×6模板及指定输入模式")
    if (root.text or "").strip() or len(list(root.iter()))>1000: raise ConversionError("SVG正文或元素数量不合法")
    if len(root)!=4 or [node.tag for node in root]!=[NS+"g"]*4 or [node.get("id") for node in root]!=["grid","numbers","labels","tracks"]:
        raise ConversionError("SVG必须包含固定顺序的四个图层")
    identifiers=[]
    for node in root.iter():
        if "id" in node.attrib:
            identifier=node.attrib["id"]
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,79}",identifier): raise ConversionError("元素ID不合法")
            identifiers.append(identifier)
    if len(identifiers)!=len(set(identifiers)): raise ConversionError("元素ID重复")
    for group in root[:3]: check_protected(group)
    tracks=root[3]
    if tracks.attrib!={"id":"tracks"} or (tracks.text or "").strip() or (tracks.tail or "").strip() or not 1<=len(tracks)<=36: raise ConversionError("轨迹图层不合法")
    occupied=set()
    for cell in tracks:
        if cell.tag!=NS+"g" or set(cell.attrib)!={"id","data-row","data-col","data-kind"}: raise ConversionError("轨迹单元结构不合法")
        r,c,kind=cell.get("data-row"),cell.get("data-col"),cell.get("data-kind")
        if r not in [str(i) for i in range(6)] or c not in [str(i) for i in range(6)] or kind not in KINDS: raise ConversionError("轨迹单元位置或方向不合法")
        row,col=int(r),int(c)
        if cell.get("id")!=f"r{row}c{col}" or (row,col) in occupied: raise ConversionError("轨迹单元重复或ID不符")
        occupied.add((row,col))
        if (cell.text or "").strip() or (cell.tail or "").strip(): raise ConversionError("轨迹单元包含非空正文")
        expected_paths=glyph_attributes(centerline(row,col,kind),expected_mode)
        if len(cell)!=len(expected_paths): raise ConversionError("轨迹图案数量不符")
        for path,attributes in zip(cell,expected_paths):
            if path.tag!=NS+"path" or path.attrib!=attributes or len(path) or (path.text or "").strip() or (path.tail or "").strip():
                raise ConversionError("轨迹几何或图案属性与受控模板不一致")
    check_connections(root)
    check_template_layers(root)
    return root


def protected_snapshot(root):
    return {group.get("id"):ET.canonicalize(ET.tostring(group,encoding="unicode")) for group in root[:3]}


def convert_bytes(raw):
    source=parse_svg_bytes(raw,"rail");target=copy.deepcopy(source);target.set("data-mode","pipe")
    before=protected_snapshot(source);route=geometry(source)
    for cell in target[3]:
        d=cell[0].get("d")
        for path in list(cell): cell.remove(path)
        for attributes in glyph_attributes(d,"pipe"): ET.SubElement(cell,NS+"path",attributes)
    output=ET.tostring(target,encoding="utf-8",xml_declaration=True)
    verified=parse_svg_bytes(output,"pipe")
    if protected_snapshot(verified)!=before or geometry(verified)!=route:
        raise ConversionError("转换后保护图层或路线几何核验失败")
    report=dict(state=source.get("data-state"),segments=len(route),protected_unchanged=True,geometry_unchanged=True,
                black_white_only=True,editable_paths=True,canvas="160mm × 160mm",view_box="0 0 600 600",
                input_sha256=digest(raw),output_sha256=digest(output),
                protected_sha256={name:digest(value.encode("utf-8")) for name,value in before.items()},
                geometry=route,boundary_endpoints=check_connections(verified),
                solution_connectivity_checked=source.get("data-state")=="solution",unique_solvability_claimed=False)
    return output,report


def convert_file(source):
    source=safe_path(source);raw=read_safe(source);output,report=convert_bytes(raw)
    if read_safe(source)!=raw: raise ConversionError("转换期间源SVG已改变")
    return output,{**report,"source_name":source.name,"source_sha256":digest(raw)}


def comparison_page(items,state):
    title="题目主题对照" if state=="puzzle" else "答案主题对照"
    sections=[]
    for source,output,report in items:
        if report["state"]!=state: continue
        original=ET.tostring(parse_svg_bytes(source,"rail"),encoding="unicode")
        changed=ET.tostring(parse_svg_bytes(output,"pipe"),encoding="unicode")
        sections.append('<section><h2>'+html.escape(report["source_name"])+' · '+str(report["segments"])+' 段轨迹</h2><div class="pair"><article><h3>原始铁路图案</h3>'+original+'</article><article><h3>转换后水管图案</h3>'+changed+'</article></div><p>网格、数字、标签的规范XML保持一致；每段中心线、方向与端点保持一致。</p></section>')
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>4967 '+title+'</title><style>body{margin:0;background:#f3f5f8;color:#203249;font:16px/1.6 "Segoe UI","Microsoft YaHei",sans-serif}main{max-width:1320px;margin:24px auto;padding:0 24px}header,section{background:white;padding:20px;border-radius:10px;margin:16px 0}header{border-top:6px solid #216f68}h1{margin:6px 0;font-size:29px}h2{font-size:20px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}article{border:1px solid #dce4eb;padding:12px}h3{margin:0;font-size:16px}svg{display:block;width:100%;height:auto}small,p{color:#55667b}@media(max-width:760px){.pair{grid-template-columns:1fr}}</style><main><header><small>4967 / 独立自造SVG演示 · 本地CLI原型</small><h1>'+title+'</h1><p>受控6×6模板：仅替换轨迹图案，不改网格、数字或路线几何。不是任意SVG转换器或谜题求解器。</p></header>'+''.join(sections or ['<section>本批未包含此类别文件。</section>'])+'<section><small>输出为可编辑的黑白SVG路径，画布160mm × 160mm。未使用客户原图；不宣称谜题唯一可解或完整Windows EXE已交付。</small></section></main></html>'


def run_batch(inputs,output):
    output=safe_path(output,existing=False)
    if output.exists(): raise ConversionError("输出目录已存在，拒绝覆盖")
    if not 1<=len(inputs)<=100: raise ConversionError("每批须为1至100个SVG文件")
    paths=[safe_path(path) for path in inputs]
    if len(set(paths))!=len(paths): raise ConversionError("同一源文件重复指定")
    items=[];reports=[]
    for index,path in enumerate(paths,1):
        converted,report=convert_file(path);raw=read_safe(path)
        if digest(raw)!=report["source_sha256"]: raise ConversionError("生成预览前源文件已改变")
        report["output_name"]=f"4967_{index:03d}_水管.svg"
        items.append((raw,converted,report));reports.append(report)
    pages={"4967_题目对照.html":comparison_page(items,"puzzle"),"4967_答案对照.html":comparison_page(items,"solution")}
    for path,(_,_,report) in zip(paths,items):
        if digest(read_safe(path))!=report["source_sha256"]: raise ConversionError("写出前源文件已改变")
    audit=dict(independent_synthetic_demo=True,converted_files=len(items),total_segments=sum(r["segments"] for r in reports),
               protected_layers_unchanged=True,all_route_geometry_unchanged=True,source_bytes_unchanged=True,
               editable_vector_output=True,arbitrary_svg_supported=False,desktop_exe_delivered=False,files=reports)
    output.mkdir()
    for _,converted,report in items:
        with (output/report["output_name"]).open("xb") as stream: stream.write(converted)
    for name,page in pages.items(): (output/name).write_text(page,encoding="utf-8")
    with (output/"4967_转换核验.json").open("x",encoding="utf-8") as stream: json.dump(audit,stream,ensure_ascii=False,indent=2)
    return audit


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",required=True,nargs="+",type=Path);parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        audit=run_batch(args.input,args.output)
        print(json.dumps({"converted_files":audit["converted_files"],"total_segments":audit["total_segments"],"all_route_geometry_unchanged":True},ensure_ascii=False))
        return 0
    except (ConversionError,OSError) as exc:
        print(str(exc),file=sys.stderr);return 2


if __name__=="__main__": raise SystemExit(main())
