# SPDX-License-Identifier: MIT
"""4967：受控6×6铁路模板与独立几何预期；只生成两份原生SVG。"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
NAMES = {"puzzle": "4967_原题.svg", "solution": "4967_答案.svg"}
ROUTE = ((0,0),(0,1),(0,2),(1,2),(2,2),(2,3),(1,3),(0,3),(0,4),
         (1,4),(2,4),(3,4),(3,3),(3,2),(3,1),(2,1),(1,1),(1,0),
         (2,0),(3,0),(4,0),(4,1),(4,2),(4,3),(5,3),(5,4),(5,5))
HINT_INDICES = (0,2,7,12,16,20,24,26)
KIND_FOR_PORTS = {frozenset(pair): kind for pair,kind in (("NS","NS"),("EW","EW"),("NE","NE"),("NW","NW"),("SE","SE"),("SW","SW"))}


def _tag(name):
    return "{" + SVG_NS + "}" + name


def _toward(cell, neighbor):
    offset = neighbor[0]-cell[0], neighbor[1]-cell[1]
    return {(-1,0):"N", (1,0):"S", (0,-1):"W", (0,1):"E"}[offset]


def route_geometry():
    """从每格的前后邻居独立推导端口、kind与规范中心线。"""
    result = []
    for index,(row,col) in enumerate(ROUTE):
        cell = row,col
        ports = ("W" if index==0 else _toward(cell,ROUTE[index-1]),
                 "E" if index==len(ROUTE)-1 else _toward(cell,ROUTE[index+1]))
        kind = KIND_FOR_PORTS[frozenset(ports)]
        left,top,cx,cy = 120+60*col,120+60*row,150+60*col,150+60*row
        right,bottom = left+60,top+60
        if kind=="NS":
            d=f"M {cx} {top} L {cx} {bottom}"; endpoints=((cx,top),(cx,bottom))
        elif kind=="EW":
            d=f"M {left} {cy} L {right} {cy}"; endpoints=((left,cy),(right,cy))
        else:
            y=top if kind[0]=="N" else bottom
            x=right if kind[1]=="E" else left
            d=f"M {cx} {y} Q {cx} {cy} {x} {cy}"; endpoints=((cx,y),(x,cy))
        result.append(dict(route_index=index,id=f"r{row}c{col}",row=row,col=col,kind=kind,d=d,
                           ports=list(ports),endpoints=[list(p) for p in endpoints]))
    assert len(result)==27 and len({item["id"] for item in result})==27
    assert {item["kind"] for item in result}=={"NS","EW","NE","NW","SE","SW"}
    return result


def _root(state):
    if state not in NAMES:
        raise ValueError("state必须是puzzle或solution")
    root=ET.Element(_tag("svg"),{"width":"160mm","height":"160mm","viewBox":"0 0 600 600",
                                 "data-demo":"4967","data-mode":"rail","data-state":state})
    grid=ET.SubElement(root,_tag("g"),{"id":"grid"})
    ET.SubElement(grid,_tag("rect"),{"x":"120","y":"120","width":"360","height":"360",
                                    "fill":"white","stroke":"black","stroke-width":"2"})
    for index in range(1,6):
        position=str(120+60*index)
        ET.SubElement(grid,_tag("line"),{"x1":position,"y1":"120","x2":position,"y2":"480","stroke":"black","stroke-width":"2"})
        ET.SubElement(grid,_tag("line"),{"x1":"120","y1":position,"x2":"480","y2":position,"stroke":"black","stroke-width":"2"})
    row_counts=Counter(row for row,col in ROUTE);column_counts=Counter(col for row,col in ROUTE)
    numbers=ET.SubElement(root,_tag("g"),{"id":"numbers"})
    for index in range(6):
        item=ET.SubElement(numbers,_tag("text"),{"x":str(150+60*index),"y":"102","font-family":"Arial",
                                                "font-size":"24","fill":"black","text-anchor":"middle"})
        item.text=str(column_counts[index])
    for index in range(6):
        item=ET.SubElement(numbers,_tag("text"),{"x":"100","y":str(158+60*index),"font-family":"Arial",
                                                "font-size":"24","fill":"black","text-anchor":"middle"})
        item.text=str(row_counts[index])
    labels=ET.SubElement(root,_tag("g"),{"id":"labels"})
    for x,y,size,text in ((120,43,22,"GRID ROUTE / DEMO 4967"),(120,70,14,"CONTROLLED VECTOR SAMPLE"),
                           (120,535,13,"6 x 6 / SYNTHETIC TRAINING DATA")):
        item=ET.SubElement(labels,_tag("text"),{"x":str(x),"y":str(y),"font-family":"Arial","font-size":str(size),"fill":"black"})
        item.text=text
    tracks=ET.SubElement(root,_tag("g"),{"id":"tracks"})
    geometry=route_geometry()
    for item in (geometry if state=="solution" else [geometry[index] for index in HINT_INDICES]):
        group=ET.SubElement(tracks,_tag("g"),{"id":item["id"],"data-row":str(item["row"]),
                                             "data-col":str(item["col"]),"data-kind":item["kind"]})
        for color,width,dash in (("black","6",None),("white","3",None),("black","10","2 9")):
            attrs={"d":item["d"],"fill":"none","stroke":color,"stroke-width":width,
                   "stroke-linecap":"round","stroke-linejoin":"round"}
            if dash:
                attrs["stroke-dasharray"]=dash
            ET.SubElement(group,_tag("path"),attrs)
    return root


def source_bytes(state):
    root=_root(state);ET.indent(root,space="  ")
    return ET.tostring(root,encoding="utf-8",xml_declaration=True)+b"\n"


def canonical_xml(element):
    return ET.canonicalize(ET.tostring(element,encoding="unicode"))


def expected_model():
    geometry=route_geometry();states={}
    for state in NAMES:
        root=ET.fromstring(source_bytes(state))
        selected=geometry if state=="solution" else [geometry[index] for index in HINT_INDICES]
        states[state]=dict(name=NAMES[state],segments=len(selected),cells=selected,
            protected_groups={child.get("id"):canonical_xml(child) for child in root[:3]},
            source_sha256=hashlib.sha256(source_bytes(state)).hexdigest())
    counts=Counter(tuple(point) for item in geometry for point in item["endpoints"])
    outside=sorted([list(point) for point,count in counts.items() if count==1])
    assert outside==[[120,150],[480,450]] and all(count in (1,2) for count in counts.values())
    return dict(schema_version=1,synthetic=True,grid_size=6,origin=[120,120],cell_size=60,
                row_counts=[5,5,5,5,4,3],column_counts=[5,5,5,6,5,1],route_cells=27,
                hint_indices=list(HINT_INDICES),solution_external_endpoints=outside,
                all_six_kinds=sorted({item["kind"] for item in geometry}),states=states,
                unique_solvability_claimed=False,customer_artwork_used=False)


def filelist(directory=BASE):
    directory=Path(directory)
    return [dict(state=state,name=name,path=str(directory/name),segments=8 if state=="puzzle" else 27) for state,name in NAMES.items()]


def generate(directory=BASE):
    directory=Path(os.path.abspath(directory))
    if not directory.is_dir():
        raise ValueError("生成目录必须已存在")
    for path in (directory,*directory.parents):
        if path.is_symlink() or getattr(path.lstat(),"st_file_attributes",0)&0x400:
            raise ValueError("生成目录不得包含链接")
    if any((directory/name).exists() or (directory/name).is_symlink() for name in NAMES.values()):
        raise ValueError("至少一份原稿已存在，全部取消，禁止覆盖")
    stage=Path(tempfile.mkdtemp(prefix="4967_自造暂存_",dir=directory));published=[]
    try:
        metadata=[]
        for item in filelist(directory):
            data=source_bytes(item["state"]);(stage/item["name"]).write_bytes(data)
            metadata.append({**item,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})
        for item in metadata:
            destination=directory/item["name"];os.link(stage/item["name"],destination);published.append(destination)
        return dict(synthetic=True,files=metadata,solution_segments=27,puzzle_segments=8,
                    row_counts=[5,5,5,5,4,3],column_counts=[5,5,5,6,5,1],
                    solution_external_endpoints=[[120,150],[480,450]],unique_solvability_claimed=False)
    except Exception:
        for path in published:
            if path.parent!=directory or not path.name.startswith("4967_"):
                raise RuntimeError("生成文件清理越界")
            path.unlink()
        raise
    finally:
        if stage.exists():
            if stage.resolve().parent!=directory.resolve() or not stage.name.startswith("4967_自造暂存_"):
                raise RuntimeError("暂存目录清理越界")
            shutil.rmtree(stage)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path,default=BASE)
    print(json.dumps(generate(parser.parse_args().output),ensure_ascii=True,indent=2))
