"""流水线画布核心引擎测试（不依赖 PyQt / QtWebEngine）。

运行：
    python -m unittest tests.test_pipeline_core -v
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.core import pipeline_templates
from app.core.pipeline import parse_graph, run_pipeline, strip_graph_for_template
from app.core.pipeline_templates import (delete_user_template, list_templates,
                                         save_user_template)


class PipelineCoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="pipeline_test_")
        self.base = self.tmp.name
        self.out = os.path.join(self.base, "out")
        os.makedirs(self.out, exist_ok=True)
        self.f1 = os.path.join(self.base, "销售一部.xlsx")
        self.f2 = os.path.join(self.base, "销售二部.xlsx")
        pd.DataFrame({
            "日期": ["2026-01-01", None, "2026-01-02", " 2026-01-03 "],
            "部门": ["销售一部", None, "销售一部", "销售一部"],
            "金额": ["1,200.50", None, "3000", " 450 "],
            "备注": ["A", None, "B", "C"],
        }).to_excel(self.f1, index=False, sheet_name="明细")
        pd.DataFrame({
            "日期": ["2026/02/01", "2026/02/02", "2026/02/03"],
            "部门": ["销售二部", "销售二部", "销售二部"],
            "金额": ["2,000", "1,500.25", "800"],
            "备注": ["D", "E", "F"],
        }).to_excel(self.f2, index=False, sheet_name="明细")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # ------------------------------------------------------------------
    def _merge_graph(self, output_name: str = "测试结果_{日期}.xlsx") -> dict:
        return {
            "version": 1,
            "nodes": [
                {"id": "f1", "type": "file", "position": {"x": 0, "y": 0},
                 "data": {"path": self.f1}},
                {"id": "f2", "type": "file", "position": {"x": 0, "y": 200},
                 "data": {"path": self.f2}},
                {"id": "m1", "type": "merge", "position": {"x": 300, "y": 100},
                 "data": {"addSource": True, "allSheets": True,
                          "alignment": "union", "ignoreEmpty": True}},
                {"id": "c1", "type": "clean", "position": {"x": 600, "y": 100},
                 "data": {"removeEmptyRows": True, "removeEmptyCols": True,
                          "stripText": True, "normalizeNumbers": True,
                          "normalizeDates": True, "dropDuplicates": False,
                          "dateFormat": "%Y-%m-%d"}},
                {"id": "o1", "type": "output", "position": {"x": 900, "y": 100},
                 "data": {"fileName": output_name, "outputDir": self.out,
                          "autoRename": True}},
            ],
            "edges": [
                {"source": "f1", "target": "m1"},
                {"source": "f2", "target": "m1"},
                {"source": "m1", "target": "c1"},
                {"source": "c1", "target": "o1"},
            ],
        }

    def test_merge_clean_output(self) -> None:
        events = []
        progress = []
        result = run_pipeline(
            self._merge_graph(),
            default_output_dir=self.out,
            emit=lambda name, payload: events.append((name, payload)),
            progress=lambda done, total: progress.append((done, total)),
        )
        self.assertTrue(result["ok"])
        output_path = result["outputs"][0]["path"]
        self.assertTrue(os.path.exists(output_path))
        frame = pd.read_excel(output_path)
        self.assertEqual(list(frame.columns[:2]), ["来源文件", "来源工作表"])
        self.assertEqual(len(frame), 6)
        self.assertEqual(int(frame["金额"].isna().sum()), 0)
        self.assertEqual(int(frame["日期"].isna().sum()), 0)
        self.assertEqual(frame["来源文件"].nunique(), 2)
        self.assertEqual(progress[-1][0], progress[-1][1])
        self.assertTrue(any(name == "node-done" for name, _ in events))

    def test_split_node(self) -> None:
        graph = self._merge_graph()
        graph["nodes"] = [node for node in graph["nodes"] if node["id"] != "o1"]
        graph["nodes"].append({
            "id": "s1", "type": "split", "position": {"x": 900, "y": 100},
            "data": {"column": "部门", "mode": "file",
                     "filenameTemplate": "{分组列值}.xlsx",
                     "skipEmpty": True,
                     "outputDir": os.path.join(self.base, "split")},
        })
        graph["edges"] = [edge for edge in graph["edges"] if edge["target"] != "o1"]
        graph["edges"].append({"source": "c1", "target": "s1"})
        result = run_pipeline(graph, default_output_dir=self.out)
        self.assertTrue(result["ok"])
        files = os.listdir(os.path.join(self.base, "split"))
        self.assertEqual(len(files), 2, files)

    def test_empty_placeholder_only_feeds_merge(self) -> None:
        graph = self._merge_graph()
        graph["nodes"][1]["data"]["path"] = ""
        result = run_pipeline(graph, default_output_dir=self.out)
        self.assertTrue(result["ok"])
        frame = pd.read_excel(result["outputs"][0]["path"])
        self.assertEqual(len(frame), 3)
        self.assertEqual(frame["来源文件"].nunique(), 1)

    def test_cycle_is_rejected(self) -> None:
        graph = self._merge_graph()
        graph["edges"].append({"source": "c1", "target": "m1"})
        with self.assertRaises(Exception):
            parse_graph(graph)

    def test_cancel_before_run(self) -> None:
        from app.core.pipeline import PipelineCancelled
        with self.assertRaises(PipelineCancelled):
            run_pipeline(self._merge_graph(), default_output_dir=self.out,
                         is_cancelled=lambda: True)

    def test_clean_without_rules_passes_through(self) -> None:
        graph = self._merge_graph()
        graph["nodes"][3]["data"] = {
            "removeEmptyRows": False, "removeEmptyCols": False,
            "stripText": False, "normalizeNumbers": False,
            "normalizeDates": False, "dropDuplicates": False,
        }
        result = run_pipeline(graph, default_output_dir=self.out)
        self.assertTrue(result["ok"])
        frame = pd.read_excel(result["outputs"][0]["path"])
        self.assertEqual(len(frame), 7)
        # 未启用清洗规则：金额保留千分位字符串，日期保留首尾空格
        self.assertEqual(str(frame["金额"].iloc[0]), "1,200.50")
        self.assertEqual(str(frame["日期"].iloc[3]), " 2026-01-03 ")

    def test_template_strips_local_paths(self) -> None:
        template = strip_graph_for_template(self._merge_graph())
        raw = repr(template)
        self.assertNotIn(self.f1, raw)
        self.assertNotIn(self.f2, raw)
        for node in template["nodes"]:
            if node["type"] == "file":
                self.assertEqual(node["data"]["path"], "")

    def test_user_template_roundtrip(self) -> None:
        original = pipeline_templates.PIPELINE_TEMPLATE_FILE
        pipeline_templates.PIPELINE_TEMPLATE_FILE = os.path.join(
            self.base, "templates.json")
        try:
            self.assertGreaterEqual(len(list_templates()), 2)
            saved = save_user_template("测试模板", self._merge_graph(), "测试")
            self.assertTrue(any(item["id"] == saved["id"]
                                for item in list_templates()))
            with open(pipeline_templates.PIPELINE_TEMPLATE_FILE,
                      encoding="utf-8") as handle:
                raw = handle.read()
            self.assertNotIn(self.f1, raw)
            self.assertTrue(delete_user_template(saved["id"]))
        finally:
            pipeline_templates.PIPELINE_TEMPLATE_FILE = original


if __name__ == "__main__":
    unittest.main()
