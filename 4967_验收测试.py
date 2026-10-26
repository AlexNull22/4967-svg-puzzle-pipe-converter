# SPDX-License-Identifier: MIT
"""4967：用独立路线/规范XML预期验收受控SVG转换，不创建位图。"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

BASE=Path(__file__).resolve().parent
NS="{http://www.w3.org/2000/svg}"


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(name,filename):
    spec=importlib.util.spec_from_file_location(name,BASE/filename)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module


def geometry_key(item):
    return (item["row"],item["col"],item["kind"],item["d"],tuple(sorted(tuple(point) for point in item["endpoints"])))


class Acceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core=load("acceptance4967_core","4967_转换引擎.py")
        cls.fixture=load("acceptance4967_fixture","4967_自造谜题.py")

    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix="4967_验收暂存_"));self.owned=self.root.resolve()

    def tearDown(self):
        checked=self.root.resolve()
        if checked!=self.owned or checked.parent!=Path(tempfile.gettempdir()).resolve() or not checked.name.startswith("4967_验收暂存_"):
            raise RuntimeError("验收清理越界")
        shutil.rmtree(checked)

    def source(self,state="puzzle"):return ET.fromstring(self.fixture.source_bytes(state))

    @staticmethod
    def raw(root):return ET.tostring(root,encoding="utf-8",xml_declaration=True)

    def rejected(self,root):
        with self.assertRaises(ValueError):self.core.convert_bytes(self.raw(root))

    def expected_geometry(self,state):
        return sorted(geometry_key(item) for item in self.fixture.expected_model()["states"][state]["cells"])

    def assert_geometry(self,root,state):
        actual=sorted(geometry_key(item) for item in self.core.geometry(root))
        self.assertEqual(actual,self.expected_geometry(state))

    def test_01_fixture_route_counts_six_kinds_endpoints_and_byte_reproduction(self):
        oracle=self.fixture.expected_model();route=self.fixture.route_geometry()
        self.assertEqual(len(route),27);self.assertEqual(len({item["id"] for item in route}),27)
        self.assertEqual({item["kind"] for item in route},{"NS","EW","NE","NW","SE","SW"})
        self.assertEqual([sum(item["row"]==i for item in route) for i in range(6)],[5,5,5,5,4,3])
        self.assertEqual([sum(item["col"]==i for item in route) for i in range(6)],[5,5,5,6,5,1])
        endpoints=Counter(tuple(point) for item in route for point in item["endpoints"])
        self.assertEqual(sorted(point for point,count in endpoints.items() if count==1),[(120,150),(480,450)])
        self.assertTrue(all(count in (1,2) for count in endpoints.values()))
        self.fixture.generate(self.root)
        for item in self.fixture.filelist(BASE):
            self.assertEqual(Path(item["path"]).read_bytes(),(self.root/item["name"]).read_bytes())
            self.assertEqual(digest(item["path"]),oracle["states"][item["state"]]["source_sha256"])
        before={p.name:p.read_bytes() for p in self.root.iterdir()}
        with self.assertRaises(ValueError):self.fixture.generate(self.root)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.iterdir()})

    def test_02_parse_both_sources_matches_all_independent_geometry_and_protected_xml(self):
        oracle=self.fixture.expected_model()
        for state in ("puzzle","solution"):
            root=self.core.parse_svg_bytes(self.fixture.source_bytes(state))
            self.assert_geometry(root,state)
            own={group.get("id"):self.fixture.canonical_xml(group) for group in root[:3]}
            self.assertEqual(own,oracle["states"][state]["protected_groups"])
            self.assertEqual(self.core.protected_snapshot(root),own)

    def test_03_output_keeps_canvas_state_all_35_geometries_and_exact_two_pipe_strokes(self):
        oracle=self.fixture.expected_model()
        for state,count in (("puzzle",8),("solution",27)):
            output,report=self.core.convert_bytes(self.fixture.source_bytes(state));root=ET.fromstring(output)
            self.assertEqual(root.attrib,{"width":"160mm","height":"160mm","viewBox":"0 0 600 600","data-demo":"4967","data-mode":"pipe","data-state":state})
            self.assertEqual(len(root[3]),count);self.assert_geometry(root,state)
            self.assertEqual({g.get("id"):self.fixture.canonical_xml(g) for g in root[:3]},oracle["states"][state]["protected_groups"])
            cells={item["id"]:item for item in oracle["states"][state]["cells"]}
            for cell in root[3]:
                item=cells[cell.get("id")]
                self.assertEqual(cell.attrib,{"id":item["id"],"data-row":str(item["row"]),"data-col":str(item["col"]),"data-kind":item["kind"]})
                self.assertEqual(len(cell),2)
                for path,color,width in zip(cell,("black","white"),("10","6")):
                    self.assertEqual(path.tag,NS+"path")
                    self.assertEqual(path.attrib,{"d":item["d"],"fill":"none","stroke":color,"stroke-width":width,"stroke-linecap":"round","stroke-linejoin":"round"})
            self.assertFalse(any(node.tag in (NS+"image",NS+"use",NS+"script") for node in root.iter()))
            self.assertEqual(report["segments"],count)
            for key in ("protected_unchanged","geometry_unchanged","black_white_only","editable_paths"):self.assertIs(report[key],True)
            self.assertIs(report["unique_solvability_claimed"],False)
            self.assertEqual(report["output_sha256"],hashlib.sha256(output).hexdigest())

    def test_04_each_of_the_six_kinds_converts_as_an_isolated_puzzle_hint(self):
        original=self.source("solution");seen=set()
        for chosen in original[3]:
            kind=chosen.get("data-kind")
            if kind in seen:continue
            seen.add(kind);root=self.source();tracks=root[3]
            for cell in list(tracks):tracks.remove(cell)
            tracks.append(copy.deepcopy(chosen))
            output,report=self.core.convert_bytes(self.raw(root))
            changed=ET.fromstring(output)[3][0]
            self.assertEqual(changed[0].get("d"),chosen[0].get("d"));self.assertEqual(changed[1].get("d"),chosen[0].get("d"))
            self.assertEqual(report["segments"],1);self.assertIs(report["solution_connectivity_checked"],False)
        self.assertEqual(seen,{"NS","EW","NE","NW","SE","SW"})

    def test_05_pipe_is_valid_only_in_pipe_mode_and_cannot_be_reprocessed_as_rail(self):
        output,_=self.core.convert_bytes(self.fixture.source_bytes("puzzle"))
        self.core.parse_svg_bytes(output,expected_mode="pipe")
        with self.assertRaises(ValueError):self.core.parse_svg_bytes(output)
        with self.assertRaises(ValueError):self.core.convert_bytes(output)
        with self.assertRaises(ValueError):self.core.parse_svg_bytes(self.fixture.source_bytes("puzzle"),expected_mode="pipe")

    def test_06_printable_labels_and_all_protected_attributes_remain_exact(self):
        root=self.source();root[2][0].text="DEMO_4967: A-B / 001 & <TEST>"
        root[2][1].set("font-weight","bold");root[2][2].set("font-family","sans-serif")
        before={g.get("id"):self.fixture.canonical_xml(g) for g in root[:3]}
        output,_=self.core.convert_bytes(self.raw(root));after=ET.fromstring(output)
        self.assertEqual({g.get("id"):self.fixture.canonical_xml(g) for g in after[:3]},before)

    def test_07_root_namespace_canvas_marker_state_and_mode_are_strict(self):
        cases=[("width","161mm"),("height","600"),("viewBox","0 0 601 600"),("data-demo","0000"),("data-state","answer"),("data-mode","pipe"),("extra","1")]
        for attribute,value in cases:
            root=self.source();root.set(attribute,value)
            with self.subTest(attribute=attribute):self.rejected(root)
        root=self.source();root.tag="{urn:4967-wrong-namespace}svg";self.rejected(root)
        root=self.source();del root.attrib["data-demo"];self.rejected(root)

    def test_08_four_layers_complete_grid_numbers_labels_and_unique_ids_required(self):
        for index in range(3):
            root=self.source()
            for child in list(root[index]):root[index].remove(child)
            with self.subTest(empty_layer=index):self.rejected(root)
        root=self.source();root[0][1].set("x1","181");self.rejected(root)
        root=self.source();root[1][0].text="7";self.rejected(root)
        root=self.source("solution");root[1][0].text="0";self.rejected(root)
        root=self.source();a,b=root[0],root[1];root.remove(a);root.remove(b);root.insert(0,b);root.insert(1,a);self.rejected(root)
        root=self.source();root[2][0].set("id","grid");self.rejected(root)

    def test_09_dtd_entities_scripts_external_images_css_and_invalid_utf8_rejected(self):
        data=self.fixture.source_bytes("puzzle")
        for raw in (b'<!DOCTYPE svg [<!ENTITY x "bad">]>'+data.split(b'?>',1)[1], b'<!-- hidden -->'+data,
                    b'<?bad instruction?>'+data,b'\xff',b'<not-xml'):
            with self.subTest(raw=raw[:25]),self.assertRaises(ValueError):self.core.convert_bytes(raw)
        for tag in ("script","image","use","foreignObject"):
            root=self.source();ET.SubElement(root[2],NS+tag,{"href":"https://example.invalid/4967.png"})
            with self.subTest(tag=tag):self.rejected(root)
        for attribute,value in (("style","fill:red"),("transform","translate(1 1)"),("onclick","alert(1)")):
            root=self.source();root[2][0].set(attribute,value);self.rejected(root)

    def test_10_protected_numeric_color_font_and_leaf_constraints(self):
        for attribute,value in (("x","-1"),("x","601"),("x","NaN"),("x","1e2"),("font-size","0"),("font-size","49"),("fill","red"),("font-family","Arial URL"),("font-weight","900")):
            root=self.source();root[2][0].set(attribute,value)
            with self.subTest(attribute=attribute,value=value):self.rejected(root)
        root=self.source();root[0][0].set("stroke-width","11");self.rejected(root)
        root=self.source();root[2][0].text="非ASCII";self.rejected(root)
        root=self.source();root[2][0].text="A"*201;self.rejected(root)
        root=self.source();ET.SubElement(root[2][0],NS+"g",{"id":"nested"});self.rejected(root)
        root=self.source();root[0].tail="UNEXPECTED";self.rejected(root)

    def test_11_track_cell_id_kind_bounds_and_occupancy_metadata_strict(self):
        for name,value in (("id","wrong"),("data-row","6"),("data-col","-1"),("data-row","00"),("data-kind","WE"),("extra","1")):
            root=self.source();root[3][0].set(name,value)
            with self.subTest(name=name,value=value):self.rejected(root)
        root=self.source();root[3].append(copy.deepcopy(root[3][0]));self.rejected(root)
        root=self.source();root[3][0].text="injected";self.rejected(root)
        root=self.source();root[3].set("transform","translate(1 1)");self.rejected(root)

    def test_12_three_source_glyphs_require_exact_paints_widths_dash_and_path_count(self):
        for index,name,value in ((0,"stroke-width","7"),(1,"stroke","black"),(1,"fill","white"),(2,"stroke-dasharray","2 8"),(0,"stroke-linecap","butt"),(0,"stroke-linejoin","bevel"),(0,"opacity","0.5")):
            root=self.source();root[3][0][index].set(name,value)
            with self.subTest(index=index,name=name):self.rejected(root)
        root=self.source();root[3][0].remove(root[3][0][2]);self.rejected(root)
        root=self.source();root[3][0].append(copy.deepcopy(root[3][0][0]));self.rejected(root)

    def test_13_centerlines_must_be_canonical_and_identical_in_all_three_glyphs(self):
        original=self.source()[3][0][0].get("d")
        variants=[original.replace("M ","m ",1),original.replace(" ","  ",1),original.replace("120","120.0",1),original+" Z",original.replace("120","121",1)]
        for d in variants:
            root=self.source()
            for path in root[3][0]:path.set("d",d)
            with self.subTest(d=d):self.rejected(root)
        root=self.source();root[3][0][1].set("d",original+" ");self.rejected(root)

    def test_14_solution_requires_unbroken_connected_route_with_two_external_ends(self):
        root=self.source("solution");root[3].remove(root[3][3]);self.rejected(root)
        root=self.source("solution");cell=root[3][3];cell.set("data-kind","EW")
        for path in cell:path.set("d","M 240 210 L 300 210")
        self.rejected(root)
        root=self.source("solution");tracks=root[3];children=list(tracks)
        for child in children:tracks.remove(child)
        for child in reversed(children):tracks.append(child)
        output,report=self.core.convert_bytes(self.raw(root));self.assert_geometry(ET.fromstring(output),"solution")
        self.assertEqual(report["boundary_endpoints"],[[0,0,"W"],[5,5,"E"]]);self.assertIs(report["solution_connectivity_checked"],True)

    def test_15_puzzle_partial_hints_need_not_be_connected_but_same_solution_rejected(self):
        root=self.source();output,report=self.core.convert_bytes(self.raw(root))
        self.assertEqual(report["segments"],8);self.assertIs(report["solution_connectivity_checked"],False)
        root.set("data-state","solution");self.rejected(root)
        root=self.source();root[3].clear();root[3].set("id","tracks");self.rejected(root)

    def test_16_batch_preflights_all_inputs_limits_and_existing_output_before_writing(self):
        good=self.root/"4967_良好.svg";good.write_bytes(self.fixture.source_bytes("puzzle"))
        bad=self.root/"4967_损坏.svg";bad.write_bytes(b'not xml');out=self.root/"4967_失败输出"
        for inputs in ([good,bad],[],[good,good],[good]*101):
            with self.subTest(length=len(inputs)),self.assertRaises(ValueError):self.core.run_batch(inputs,out)
            self.assertFalse(out.exists())
        existing=self.root/"4967_已存在";existing.mkdir();marker=existing/"4967_保留.txt";marker.write_text("keep",encoding="utf-8")
        with self.assertRaises(ValueError):self.core.run_batch([good],existing)
        self.assertEqual(marker.read_text(encoding="utf-8"),"keep")
        with mock.patch.object(self.core,"MAX_BYTES",len(good.read_bytes())-1),self.assertRaises(ValueError):self.core.run_batch([good],out)
        self.assertFalse(out.exists())

    def test_17_real_cli_batch_five_outputs_are_deterministic_truthful_and_source_unchanged(self):
        sources=[Path(item["path"]) for item in self.fixture.filelist(BASE)];before={p.name:digest(p) for p in sources}
        one,two=self.root/"4967_批量一",self.root/"4967_批量二"
        command=[sys.executable,"-B",str(BASE/"4967_转换引擎.py"),"--input",*map(str,sources),"--output",str(one)]
        result=subprocess.run(command,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr.decode("utf-8","replace"));self.assertEqual(json.loads(result.stdout)["total_segments"],35)
        audit=self.core.run_batch(sources,two)
        names={"4967_001_水管.svg","4967_002_水管.svg","4967_转换核验.json","4967_题目对照.html","4967_答案对照.html"}
        self.assertEqual({p.name for p in one.iterdir()},names)
        for name in names:self.assertEqual((one/name).read_bytes(),(two/name).read_bytes())
        self.assertEqual(json.loads((one/"4967_转换核验.json").read_text(encoding="utf-8")),audit)
        self.assertEqual((audit["converted_files"],audit["total_segments"]),(2,35))
        for key in ("source_bytes_unchanged","all_route_geometry_unchanged","protected_layers_unchanged","editable_vector_output"):self.assertIs(audit[key],True)
        for key in ("arbitrary_svg_supported","desktop_exe_delivered"):self.assertIs(audit[key],False)
        for index,state in enumerate(("puzzle","solution"),1):
            output=one/f"4967_{index:03d}_水管.svg";report=audit["files"][index-1]
            self.assertEqual(digest(output),report["output_sha256"]);self.assertEqual(before[sources[index-1].name],report["source_sha256"])
            self.assert_geometry(ET.fromstring(output.read_bytes()),state)
        for name in ("4967_题目对照.html","4967_答案对照.html"):
            text=(one/name).read_text(encoding="utf-8");self.assertEqual(text.count("<svg "),2);self.assertNotIn(str(BASE),text)
        self.assertEqual(before,{p.name:digest(p) for p in sources})
        snapshot={p.name:p.read_bytes() for p in one.iterdir()}
        result=subprocess.run(command,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,2);self.assertEqual(snapshot,{p.name:p.read_bytes() for p in one.iterdir()})

    def test_18_changed_source_and_real_windows_junction_paths_are_refused(self):
        real=self.root/"4967_真实目录";real.mkdir();source=real/"4967_输入.svg";original=self.fixture.source_bytes("puzzle");source.write_bytes(original)
        converter=self.core.convert_bytes
        def changed(raw):
            result=converter(raw);source.write_bytes(original+b"\n");return result
        try:
            with mock.patch.object(self.core,"convert_bytes",side_effect=changed),self.assertRaises(ValueError):self.core.convert_file(source)
        finally:source.write_bytes(original)
        if os.name!="nt":self.skipTest("Windows目录连接点专项")
        junction=self.root/"4967_连接入口"
        result=subprocess.run(["cmd","/c","mklink","/J",str(junction),str(real)],capture_output=True)
        if result.returncode:self.skipTest("系统不允许目录连接点")
        try:
            with self.assertRaises(ValueError):self.core.convert_file(junction/source.name)
            with self.assertRaises(ValueError):self.core.run_batch([source],junction/"4967_结果")
            self.assertEqual(source.read_bytes(),original);self.assertEqual({p.name for p in real.iterdir()},{source.name})
        finally:
            if junction.parent!=self.root or not junction.name.startswith("4967_"):raise RuntimeError("连接点清理越界")
            junction.rmdir()


class TimedResult(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.details=[]
    def startTest(self,test):super().startTest(test);self.current=dict(test=test._testMethodName,status="running");self.began=time.perf_counter()
    def addSuccess(self,test):super().addSuccess(test);self.current["status"]="passed"
    def addFailure(self,test,error):super().addFailure(test,error);self.current["status"]="failure"
    def addError(self,test,error):super().addError(test,error);self.current["status"]="error"
    def addSkip(self,test,reason):super().addSkip(test,reason);self.current.update(status="skipped",reason=reason)
    def addSubTest(self,test,subtest,error):
        super().addSubTest(test,subtest,error)
        if error:self.current["status"]="failure" if issubclass(error[0],test.failureException) else "error"
    def stopTest(self,test):self.current["elapsed_seconds"]=round(time.perf_counter()-self.began,6);self.details.append(self.current);super().stopTest(test)


def main():
    parser=argparse.ArgumentParser(add_help=False);parser.add_argument("--report",type=Path);args,remaining=parser.parse_known_args()
    names=["4967_转换引擎.py","4967_自造谜题.py","4967_验收测试.py"]
    before={name:digest(BASE/name) for name in names}
    fixture=load("report4967_fixture","4967_自造谜题.py")
    source_hashes={item["name"]:digest(item["path"]) for item in fixture.filelist(BASE)};began=time.perf_counter()
    result=unittest.main(argv=[sys.argv[0],*remaining],testRunner=unittest.TextTestRunner(verbosity=2,resultclass=TimedResult),exit=False).result
    after={name:digest(BASE/name) for name in names};unchanged=source_hashes=={item["name"]:digest(item["path"]) for item in fixture.filelist(BASE)}
    successful=result.wasSuccessful() and before==after and unchanged
    if args.report:
        target=Path(os.path.abspath(args.report))
        if not target.parent.is_dir() or not target.name.startswith("4967_") or target.suffix!=".json" or target.is_symlink():raise ValueError("报告须为4967前缀JSON普通路径")
        for item in (target.parent,*target.parent.parents):
            if item.is_symlink() or getattr(item.lstat(),"st_file_attributes",0)&0x400:raise ValueError("报告路径含链接")
        report=dict(schema_version=1,tests_run=result.testsRun,passed=sum(row["status"]=="passed" for row in result.details),
                    failures=sum(row["status"]=="failure" for row in result.details),errors=sum(row["status"]=="error" for row in result.details),skipped=len(result.skipped),
                    successful=successful,elapsed_seconds=round(time.perf_counter()-began,6),per_test=result.details,
                    environment=dict(python=platform.python_version(),system=platform.system()),code_sha256=after,code_unchanged_during_tests=before==after,
                    source_files_sha256=source_hashes,all_sources_unchanged=unchanged,puzzle_segments=8,solution_segments=27,total_converted_segments=35,
                    independent_six_kinds_verified=True,protected_groups_canonical_xml_verified=True,all_centerlines_and_endpoints_verified=True,
                    independent_oracle="Route adjacency and endpoint tuples, independent protected C14N and exact glyph attribute checks",
                    network_used=False,raster_generated=False,customer_artwork_used=False,unique_solvability_claimed=False)
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    raise SystemExit(0 if successful else 1)


if __name__=="__main__":main()
