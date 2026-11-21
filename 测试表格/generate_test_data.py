# -*- coding: utf-8 -*-
"""生成 Excel 批量工作台的完整测试数据。

运行：
    python generate_test_data.py

生成内容覆盖：合并、拆分、格式化、提取、替换、CSV/Excel 转换、
模板填充、20 行预览、空工作表、空分组、脏数据、超链接、批注、
合并单元格、前导零等场景。
"""
import csv
import os
import shutil
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

HEADER_FILL = PatternFill("solid", fgColor="DCE6F2")
HEADER_FONT = Font(bold=True, color="1F3864")
THIN = Side(style="thin", color="B7C9E2")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _prepare_dir(name):
    folder = os.path.join(BASE_DIR, name)
    os.makedirs(folder, exist_ok=True)
    for filename in os.listdir(folder):
        path = os.path.join(folder, filename)
        if os.path.isfile(path):
            os.remove(path)
    return folder


def _style_sheet(ws, headers, rows_count, widths=None):
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
    for row in ws.iter_rows(min_row=2, max_row=rows_count + 1,
                            max_col=len(headers)):
        for cell in row:
            cell.border = BORDER
            cell.alignment = Alignment(vertical="center", wrap_text=True)
    if widths:
        for index, width in enumerate(widths, start=1):
            ws.column_dimensions[ws.cell(1, index).column_letter].width = width
    ws.freeze_panes = "A2"


def add_sheet(wb, name, headers, rows, widths=None,
              text_columns=(), date_columns=(), hyperlinks=None,
              comments=None, merges=None):
    ws = wb.create_sheet(name)
    ws.append(headers)
    for row in rows:
        ws.append(row)

    for row_index, row in enumerate(rows, start=2):
        for col_index, value in enumerate(row, start=1):
            cell = ws.cell(row_index, col_index)
            if headers[col_index - 1] in text_columns and isinstance(value, str):
                cell.number_format = "@"
            if headers[col_index - 1] in date_columns and isinstance(
                    value, (date, datetime)):
                cell.number_format = "yyyy-mm-dd"

    for (row_index, col_index), url in (hyperlinks or {}).items():
        cell = ws.cell(row_index, col_index)
        cell.hyperlink = url
        cell.style = "Hyperlink"

    for (row_index, col_index), text in (comments or {}).items():
        cell = ws.cell(row_index, col_index)
        cell.comment = Comment(text, "测试数据")

    for cell_range in (merges or []):
        ws.merge_cells(cell_range)

    _style_sheet(ws, headers, len(rows), widths)
    return ws


def save_workbook(wb, path):
    wb.remove(wb["Sheet"]) if "Sheet" in wb.sheetnames else None
    wb.active = 0
    wb.save(path)
    print("[生成]", path)


# ---------------------------------------------------------------------------
# 01 合并工作表
# ---------------------------------------------------------------------------
def build_merge_cases():
    folder = _prepare_dir("01_合并工作表")

    jan = [
        ["2026-01-05", "销售一部", "传感器", 120, 36000],
        ["2026-01-12", "销售二部", "电机", 86, 25800],
        ["2026-01-20", "销售一部", "传感器", 150, 45000],
        ["2026-01-28", "销售三部", "控制器", 45, 13500],
        ["2026-01-07", "销售二部", "控制器", 60, 18000],
        ["2026-01-15", "销售一部", "电机", 75, 22500],
        ["2026-01-22", "销售三部", "传感器", 95, 28500],
        ["2026-01-30", "销售二部", "电机", 110, 33000],
    ]
    feb = [
        ["2026-02-03", "销售二部", "电机", 92, 27600],
        ["2026-02-11", "销售一部", "控制器", 38, 11400],
        ["2026-02-19", "销售三部", "传感器", 175, 52500],
        ["2026-02-26", "销售二部", "电机", 70, 21000],
        ["2026-02-05", "销售一部", "传感器", 130, 39000],
        ["2026-02-14", "销售三部", "控制器", 52, 15600],
        ["2026-02-21", "销售二部", "传感器", 88, 26400],
        ["2026-02-28", "销售一部", "电机", 66, 19800],
    ]
    wb = Workbook()
    add_sheet(wb, "1月",
              ["日期", "部门", "产品", "销量", "销售额"], jan,
              widths=[13, 12, 11, 8, 11])
    add_sheet(wb, "2月",
              ["日期", "部门", "产品", "销量", "销售额"], feb,
              widths=[13, 12, 11, 8, 11])
    save_workbook(wb, os.path.join(folder, "销售数据_一季度.xlsx"))

    mar = [
        ["2026-03-04", "销售一部", "传感器", 133, 39900, "补货", "张伟"],
        ["2026-03-13", "销售三部", "控制器", 52, 15600, "样机", "王强"],
        ["2026-03-22", "销售二部", "电机", 88, 26400, "常规订单", "李娜"],
        ["2026-03-08", "销售一部", "电机", 77, 23100, "加急", "张伟"],
        ["2026-03-17", "销售二部", "传感器", 101, 30300, "老客户", "李娜"],
        ["2026-03-29", "销售三部", "控制器", 64, 19200, "", "王强"],
    ]
    apr = [
        ["2026-04-02", "销售三部", "控制器", 61, 18300, "常规订单", "王强"],
        ["2026-04-15", "销售一部", "传感器", 148, 44400, "大批量", "张伟"],
        ["2026-04-25", "销售二部", "电机", 79, 23700, "退换后补发", "李娜"],
        ["2026-04-09", "销售一部", "控制器", 42, 12600, "新客户", "张伟"],
        ["2026-04-18", "销售三部", "传感器", 96, 28800, "加急", "王强"],
        ["2026-04-27", "销售二部", "电机", 55, 16500, "", "李娜"],
    ]
    wb = Workbook()
    add_sheet(wb, "3月",
              ["日期", "部门", "产品", "销量", "销售额", "备注 ", "负责人"],
              mar, widths=[13, 12, 11, 8, 11, 14, 9])
    add_sheet(wb, "4月",
              ["日期", "部门", "产品", "销量", "销售额", "备注 ", "负责人"],
              apr, widths=[13, 12, 11, 8, 11, 14, 9])
    save_workbook(wb, os.path.join(folder, "销售数据_二季度.xlsx"))

    may = [
        ["2026-05-08", "销售一部", "传感器", 105],
        ["2026-05-18", "销售三部", "电机", 67],
        ["2026-05-06", "销售二部", "控制器", 54],
        ["2026-05-22", "销售一部", "电机", 89],
        ["2026-05-29", "销售三部", "传感器", 112],
    ]
    wb = Workbook()
    add_sheet(wb, "空表(仅表头)",
              ["日期", "部门", "产品", " 销量 "], [],
              widths=[13, 12, 11, 8])
    add_sheet(wb, "5月",
              ["日期", "部门", "产品", " 销量 "], may,
              widths=[13, 12, 11, 8])
    save_workbook(wb, os.path.join(folder, "销售数据_含空表.xlsx"))


# ---------------------------------------------------------------------------
# 02 拆分工作表
# ---------------------------------------------------------------------------
def build_split_case():
    folder = _prepare_dir("02_拆分工作表")

    departments_1 = (
        ["研发部"] * 6 + ["研发/测试"] * 2 + ["销售部"] * 6
        + ["行政部"] * 4 + ["市场部"] * 3 + ["财务部"] * 2 + [""]
    )
    cities = ["武汉", "成都", "西安", "重庆", "北京", "上海"]
    names = ["张伟", "李娜", "王强", "刘洋", "陈静", "赵磊",
             "孙敏", "周涛", "吴磊", "郑晓", "冯丽", "何军"]
    rows_1 = []
    for index, department in enumerate(departments_1, start=1):
        rows_1.append([
            f"E{index:03d}",
            names[(index - 1) % len(names)] + ("" if index <= 12 else str(index)),
            department,
            cities[(index - 1) % len(cities)],
            6000 + index * 350,
            f"2026/{(index - 1) % 6 + 1}/{(index - 1) % 27 + 1:02d}",
            "待分配" if not department else ("跨部门" if "/" in department else ""),
        ])

    departments_2 = ["销售部"] * 4 + ["市场部"] * 3 + ["行政部"] * 2 + [""]
    rows_2 = []
    for index, department in enumerate(departments_2, start=1):
        rows_2.append([
            f"E2{index:02d}",
            names[(index - 1) % len(names)],
            department,
            cities[(index + 1) % len(cities)],
            7000 + index * 400,
            f"2026-07-{index:02d}",
            "第二张表" if department else "空部门",
        ])

    wb = Workbook()
    add_sheet(wb, "员工1",
              ["工号", "姓名", "部门", "城市", "薪资", "入职日期", "备注"],
              rows_1, widths=[10, 12, 13, 9, 10, 13, 12])
    add_sheet(wb, "员工2",
              ["工号", "姓名", "部门", "城市", "薪资", "入职日期", "备注"],
              rows_2, widths=[10, 12, 13, 9, 10, 13, 12])
    save_workbook(wb, os.path.join(folder, "员工汇总表.xlsx"))


# ---------------------------------------------------------------------------
# 03 批量格式化
# ---------------------------------------------------------------------------
def build_format_case():
    folder = _prepare_dir("03_批量格式化")

    rows = [
        ["E001", "  张伟 ", "2026/3/1", "研发部", "138 0013 8001",
         " 12,800.50 ", "正常入职", None],
        ["E002", "李娜", "2026-03-05", "销售部", "13900138002",
         "￥9,600", "含中文逗号，备注", None],
        ["E003", "　王强　", "03/12/2026", "研发部", "137-0013-8003",
         "1.2万", "试用期", None],
        ["E004", "刘洋", "2026.03.20", "行政部", "１３６００１３８００４",
         "15%", "", None],
        ["E005", "陈静", "2026年3月21日", "销售部", "135 0013 8005",
         "00123", "重复校验", None],
        ["E005", "陈静", "2026年3月21日", "销售部", "135 0013 8005",
         "00123", "重复校验", None],
        [None, None, None, None, None, None, None, None],
        ["E006", " 赵磊 ", "2026/3/25", "市场部", "13400138006",
         "13800138000", "手机号不应转数字", None],
        ["E007", "孙敏", "2026-3-28", "研发部", "13300138007",
         "1,234", "远程办公", None],
        ["", "周涛", "2026/4/1", "行政部", "13200138008",
         "￥ 8,800.00", "工号缺失", None],
        ["E008", "吴磊", "2026年3月22日", "研发/测试", "131 0013 8009",
         "3,000", "跨部门", None],
        ["E009", "郑晓", "2026/3/23", "财务部", "13000138010",
         "12.5", "新建", None],
        ["E010", "冯丽", "2026.3.24", "销售部", "18900138011",
         "12,345.67", "大客户", None],
        ["E011", "何军", "2026/3/25 09:30", "市场部", "18800138012",
         "0.5", "含时间", None],
        ["E012", "高敏", date(2026, 3, 26), "行政部", "18700138013",
         "100", "正常", None],
        ["E013", "林峰", date(2026, 3, 27), "研发部", "18600138014",
         "2,000.00", "正常", None],
        ["E014", "马丽", date(2026, 3, 28), "销售部", "18500138015",
         "￥7,500", "正常", None],
        ["E015", "郭强", "2026-03-29", "市场部", "18400138016",
         "9,999", "正常", None],
        ["E016", "罗静", "三月十五日", "财务部", "18300138017",
         "1,000", "日期无法解析（中文数字）", None],
        ["E017", "梁宇", "2026/3/31", "研发部", "18200138018",
         "2,500", "正常", None],
        ["E018", "宋佳", "2026-04-01", "销售部", "18100138019",
         "3,600", "正常", None],
        ["E019", "唐磊", "2026年4月2日", "行政部", "18000138020",
         "4,700", "正常", None],
        ["E020", "许静", "2026/4/3", "市场部", "17900138021",
         "5,800", "正常", None],
        ["E021", "邓超", "2026-13-40", "财务部", "17800138022",
         "6,900", "日期无法解析（月份越界）", None],
    ]

    wb = Workbook()
    add_sheet(
        wb, "脏数据",
        ["工号", "姓名", "入职日期", "部门", "电话", "工资", "备注", "空列"],
        rows, widths=[9, 12, 14, 12, 18, 13, 24, 8],
        text_columns=("工号", "电话", "备注"),
        hyperlinks={
            (2, 7): "https://example.com/orders/001",
            (4, 7): "https://example.com/orders/003",
            (9, 7): "https://example.com/employees/006",
        },
        comments={
            (2, 2): "姓名前后有半角空格",
            (3, 3): "日期是 月/日/年 格式",
            (4, 2): "姓名前后有全角空格",
            (10, 7): "工号为空，格式化后应保留并在日志提示",
        },
    )

    second_rows = [
        ["S001", "张伟", "研发部", "2026-03-01", 9000, "合并单元格示例"],
        ["S002", "李娜", "销售部", "2026-03-02", 8000, "正常"],
        ["S002", "李娜", "销售部", "2026-03-02", 8000, "重复行"],
        ["S003", "王强", "研发部", "2026-03-03", 9500, "正常"],
        ["S004", "刘洋", "行政部", "2026-03-04", 7000, ""],
        ["S005", "陈静", "销售部", "2026-03-05", 8500, "正常"],
        ["S006", "赵磊", "市场部", "2026-03-06", 7500, "正常"],
        ["S007", "孙敏", "研发部", "2026-03-07", 10000, "正常"],
    ]
    ws = add_sheet(
        wb, "第二张表",
        ["工号", "姓名", "部门", "入职日期", "工资", "备注"],
        second_rows, widths=[10, 12, 12, 14, 10, 20],
        text_columns=("工号", "备注"),
        comments={(3, 6): "第二张表的批注"},
    )
    # 合并两个数据单元格，验证格式化后不保留合并单元格
    ws.merge_cells("A5:A6")
    ws["A5"] = "S004-S005 合并"
    ws["A5"].alignment = Alignment(vertical="center")

    formula_rows = [
        ["合计", "=SUM(1,2,3)", "公式结果只保留值/文本，不保留公式"],
        ["百分比", 0.156, "数字格式测试"],
        ["文本数字", "12,345.60", "数字统一测试"],
    ]
    add_sheet(
        wb, "公式与格式",
        ["项目", "数值", "说明"], formula_rows, widths=[12, 14, 36],
        text_columns=("项目", "说明"))

    save_workbook(wb, os.path.join(folder, "脏数据_员工表.xlsx"))


# ---------------------------------------------------------------------------
# 04 提取与替换
# ---------------------------------------------------------------------------
def build_extract_replace_case():
    folder = _prepare_dir("04_提取与替换")

    customers = [
        ["001", " 迅达电子（重庆） ", "刘芳", "１３８００１３９００１",
         "重庆市渝北区", "老客户", "001234567890123X", 12000.50, "2026-03-01"],
        ["002", "恒信贸易", " 周杰 ", "139 0013 9002",
         "成都市武侯区", "", "000000000000002", 8000, "2026-03-02"],
        ["003", "迅达电子·成都分公司", "吴磊", "137-0013-9003",
         "成都市高新区", "待回访", "000000000000003", 15000, "2026-03-03"],
        ["004", "天成机械", "郑晓", "13600139004",
         "武汉市洪山区", "新签约", "000000000000004", 9000, "2026-03-04"],
        ["005", " 博众 光电 ", "冯丽", "135 0013 9005",
         "西安市雁塔区", "", "000000000000005", 11000, "2026-03-05"],
        ["006", "迅达电子 武汉办事处", "何军", "13400139006",
         "武汉市江汉区", "老客户", "000000000000006", 7000, "2026-03-06"],
        ["007", "Excel科技", "徐丽", "13300139007",
         "北京市海淀区", "Excel 测试", "000000000000007", 5000, "2026-03-07"],
        ["008", "excel贸易", "孙强", "13200139008",
         "北京市朝阳区", "excel 小写", "000000000000008", 4500, "2026-03-08"],
        ["009", "EXCEL集团", "马超", "13100139009",
         "上海市浦东新区", "EXCEL 大写", "000000000000009", 18000, "2026-03-09"],
        ["010", "旧名称公司", "朱婷", "13000139010",
         "广州市天河区", "旧名称", "000000000000010", 6000, "2026-03-10"],
        ["011", "天宇电子", "胡军", "18900139011",
         "深圳市南山区", "A-001 项目", "000000000000011", 22000, "2026-03-11"],
        ["012", "天宇电子", "郭敏", "18800139012",
         "深圳市福田区", "A-002 项目", "000000000000012", 21000, "2026-03-12"],
        ["013", "恒信贸易", "林芳", "18700139013",
         "成都市锦江区", "2026-03-13 续约", "000000000000013", 7500, "2026-03-13"],
        ["014", "迅达电子", "高伟", "18600139014",
         "重庆市江北区", "2026-03-14 签约", "000000000000014", 9800, "2026-03-14"],
        ["015", "博众光电", "罗静", "18500139015",
         "西安市高新区", "老客户", "000000000000015", 13000, "2026-03-15"],
        ["016", "恒信贸易", "梁宇", "18400139016",
         "成都市青羊区", "", "000000000000016", 6600, "2026-03-16"],
        ["017", "迅达电子（重庆）", "宋佳", "18300139017",
         "重庆市南岸区", "待回访", "000000000000017", 8800, "2026-03-17"],
        ["018", "天成机械", "唐磊", "18200139018",
         "武汉市武昌区", "新签约", "000000000000018", 14000, "2026-03-18"],
        ["019", "博众 光电", "许静", "18100139019",
         "西安市未央区", "", "000000000000019", 9200, "2026-03-19"],
        ["020", "迅达电子", "邓超", "18000139020",
         "重庆市渝中区", "A-020 项目", "000000000000020", 10500, "2026-03-20"],
        ["021", "北辰贸易", "刘敏", "17900139021",
         "天津市和平区", "新客户", "000000000000021", 5600, "2026-03-21"],
        ["022", "北辰贸易", "王芳", "17800139022",
         "天津市河西区", "", "000000000000022", 6100, "2026-03-22"],
        ["023", "天宇电子", "李强", "17700139023",
         "深圳市宝安区", "老客户", "000000000000023", 23000, "2026-03-23"],
        ["024", "迅达电子", "张敏", "17600139024",
         "重庆市九龙坡区", "2026-03-24 签约", "000000000000024", 7700, "2026-03-24"],
    ]
    wb = Workbook()
    add_sheet(
        wb, "客户联系",
        ["序号", "客户名称", "联系人", "电话", "地址", "备注",
         "统一社会信用代码", "金额", "签约日期"],
        customers, widths=[7, 24, 10, 18, 18, 20, 22, 10, 14],
        text_columns=("序号", "电话", "统一社会信用代码", "签约日期"))

    extra = [
        ["101", "备用客户甲", "甲一", "15900139001", "武汉市", "备用"],
        ["102", "备用客户乙", "乙二", "15900139002", "长沙市", ""],
        ["103", "迅达电子", "丙三", "15900139003", "重庆市", "备用"],
        ["104", "恒信贸易", "丁四", "15900139004", "成都市", "备用"],
        ["105", "旧名称公司", "戊五", "15900139005", "广州市", "旧名称"],
        ["106", "北辰贸易", "己六", "15900139006", "天津市", ""],
        ["107", "博众光电", "庚七", "15900139007", "西安市", "备用"],
        ["108", "天成机械", "辛八", "15900139008", "武汉市", "备用"],
        ["109", "Excel科技", "壬九", "15900139009", "北京市", "Excel 测试"],
        ["110", "备用客户丙", "癸十", "15900139010", "长沙市", ""],
    ]
    add_sheet(
        wb, "备用客户",
        ["序号", "客户名称", "联系人", "电话", "地址", "备注"],
        extra, widths=[7, 24, 10, 18, 18, 20])
    save_workbook(wb, os.path.join(folder, "客户联系表.xlsx"))

    mapping = [
        ["迅达电子", "迅达科技"],
        ["恒信贸易", "恒信集团"],
        ["北京", "北京市"],
        ["A-001", "A001"],
        ["^A-(\\d+)$", "A\\1"],
        ["(\\d{4})-(\\d{2})-(\\d{2})", "\\3/\\2/\\1"],
        ["excel", "Excel"],
        ["旧名称", "新名称"],
        ["", "空查找内容会被忽略"],
    ]
    wb = Workbook()
    add_sheet(wb, "替换规则", ["查找内容", "替换为"], mapping,
              widths=[32, 26])
    add_sheet(wb, "说明", ["说明"],
              [["只读取第一张工作表；勾选“使用正则表达式”后，第 5、6 条规则才按正则执行。"]],
              widths=[80])
    save_workbook(wb, os.path.join(folder, "替换对照表.xlsx"))


# ---------------------------------------------------------------------------
# 05 格式转换
# ---------------------------------------------------------------------------
def build_convert_case():
    folder = _prepare_dir("05_格式转换")

    headers = ["订单号", "客户", "商品", "数量", "金额", "日期", "备注"]
    rows = [
        ["00123", "恒信贸易", "传感器,工业级", 20, 12000, "2026-03-01", "含逗号"],
        ["00124", "天成机械", "伺服电机", 5, 18500, "2026-03-01", ""],
        ["00125", "博众光电", "控制器", 8, 9600, "2026-03-02", "引号\"测试\""],
        ["00126", "迅达科技", "工业相机", 3, 27000, "2026-03-02", "普通"],
        ["00127", "恒信贸易", "传感器,工业级", 12, 7200, "2026-03-03",
         "多行\n备注第二行"],
        ["00128", "天成机械", "伺服电机", 7, 25900, "2026-03-03", ""],
        ["00129", "博众光电", "控制器", 15, 18000, "2026-03-04", "含,逗号"],
        ["00130", "迅达科技", "工业相机", 2, 18000, "2026-03-04", "普通"],
        ["00131", "恒信贸易", "传感器", 9, 5400, "2026-03-05", ""],
        ["00132", "天成机械", "伺服电机", 4, 14800, "2026-03-05", "普通"],
    ]
    # UTF-8 BOM
    with open(os.path.join(folder, "订单数据_UTF8.csv"), "w",
              encoding="utf-8-sig", newline="") as fp:
        writer = csv.writer(fp, lineterminator="\r\n")
        writer.writerow(headers)
        writer.writerows(rows)
    print("[生成]", os.path.join(folder, "订单数据_UTF8.csv"))

    # UTF-8 无 BOM
    with open(os.path.join(folder, "订单数据_UTF8无BOM.csv"), "w",
              encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp, lineterminator="\r\n")
        writer.writerow(headers)
        writer.writerows(rows[:8])
    print("[生成]", os.path.join(folder, "订单数据_UTF8无BOM.csv"))

    # GBK
    gbk_rows = [
        ["00201", "重庆百货", "传感器", 30, 18000, "2026-04-01", "GBK 编码"],
        ["00202", "成都商贸", "电机", 6, 22200, "2026-04-01", ""],
        ["00203", "西安实业", "控制器", 10, 12000, "2026-04-02", "中文不乱码"],
        ["00204", "武汉科技", "工业相机", 2, 18000, "2026-04-02", ""],
        ["00205", "重庆百货", "传感器", 18, 10800, "2026-04-03", "含逗号,测试"],
        ["00206", "成都商贸", "电机", 8, 29600, "2026-04-03", ""],
        ["00207", "西安实业", "控制器", 5, 6000, "2026-04-04", ""],
        ["00208", "武汉科技", "工业相机", 1, 9000, "2026-04-04", "普通"],
    ]
    with open(os.path.join(folder, "订单数据_GBK.csv"), "w",
              encoding="gbk", newline="") as fp:
        writer = csv.writer(fp, lineterminator="\r\n")
        writer.writerow(headers)
        writer.writerows(gbk_rows)
    print("[生成]", os.path.join(folder, "订单数据_GBK.csv"))

    wb = Workbook()
    for sheet_name, start in (("订单1", 0), ("订单2", 5)):
        data = []
        for offset in range(8):
            data.append([
                f"PO{start + offset + 1:04d}",
                "恒信贸易" if offset % 2 == 0 else "博众光电",
                "传感器,工业级" if offset % 3 == 0 else "控制器",
                offset + 2,
                6000 + offset * 300,
                f"2026-05-{offset + 1:02d}",
                "含逗号,和\"引号\"" if offset == 0 else "",
            ])
        add_sheet(wb, sheet_name, headers, data,
                  widths=[12, 14, 16, 8, 10, 12, 22],
                  text_columns=("订单号",))
    save_workbook(wb, os.path.join(folder, "订单数据.xlsx"))

    # 只有表头的 CSV，用于测试空数据转换
    with open(os.path.join(folder, "空订单表.csv"), "w",
              encoding="utf-8-sig", newline="") as fp:
        writer = csv.writer(fp, lineterminator="\r\n")
        writer.writerow(headers)
    print("[生成]", os.path.join(folder, "空订单表.csv"))


# ---------------------------------------------------------------------------
# 06 模板填充
# ---------------------------------------------------------------------------
def build_template_case():
    folder = _prepare_dir("06_模板填充")

    rows = [
        ["001", "张伟", "研发部", 12000, "2026-12-01", "新员工"],
        ["002", "李娜", "销售部", 9800, "2026-12-02", ""],
        ["003", "王强", "财务部", 10500, "2026-12-03", "试用期"],
        ["004", "刘洋", "行政部", 7600, "2026-12-04", ""],
        ["005", "陈静", "市场部", 8800, "2026-12-05", "应届生"],
        ["006", "赵磊", "研发部", 13500, "2026-12-06", ""],
        ["007", "孙敏", "销售部", 9200, "2026-12-07", "转岗"],
        ["008", "周涛", "财务部", 11000, "2026-12-08", ""],
    ]
    wb = Workbook()
    add_sheet(wb, "员工数据",
              ["编号", "姓名", "部门", "金额", "日期", "备注"],
              rows, widths=[9, 10, 12, 12, 13, 14],
              text_columns=("编号", "姓名", "部门", "备注"))
    save_workbook(wb, os.path.join(folder, "员工数据.xlsx"))

    wb = Workbook()
    ws = wb.create_sheet("通知书")
    ws.merge_cells("A1:D1")
    ws["A1"] = "入 职 通 知 书"
    ws["A1"].font = Font(bold=True, size=20, color="1F3864")
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 36

    ws.merge_cells("A3:D3")
    ws["A3"] = "尊敬的 {{姓名}} 先生 / 女士："
    ws["A3"].font = Font(size=12)
    ws["A4"] = "部门：{{部门}}"
    ws["A4"].font = Font(size=11)
    ws["A5"] = "编号：{{编号}}"
    ws["A5"].font = Font(size=11)
    ws["A6"] = "金额："
    ws["B6"] = "{{金额}}"
    ws["B6"].number_format = "#,##0.00"
    ws["B7"] = "{{日期}}"
    ws["B7"].number_format = "yyyy-mm-dd"
    ws["A7"] = "日期："
    ws.merge_cells("A9:D9")
    ws["A9"] = "请于 {{日期}} 到 {{部门}} 办理入职手续。"
    ws["A9"].font = Font(size=11)
    ws.merge_cells("A11:D11")
    ws["A11"] = "第 {{序号}} 份 · {{模板名}}"
    ws["A11"].font = Font(size=9, italic=True, color="808080")

    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 18
    ws.sheet_view.showGridLines = False
    save_workbook(wb, os.path.join(folder, "入职通知书模板.xlsx"))


# ---------------------------------------------------------------------------
# 07 数据透视
# ---------------------------------------------------------------------------
def build_pivot_case():
    folder = _prepare_dir("07_数据透视")

    departments = ["销售部", "市场部", "财务部", "行政部"]
    regions = ["华东", "华南", "华北"]
    products = ["传感器", "控制器", "工业相机"]
    rows = []
    for index in range(24):
        rows.append([
            departments[index % len(departments)],
            regions[index % len(regions)],
            products[index % len(products)],
            10 + index,
            1000 + index * 350,
            f"2026-08-{index % 28 + 1:02d}",
            ["张伟", "李娜", "王强", "赵磊"][index % 4],
        ])

    wb = Workbook()
    add_sheet(
        wb, "销售明细",
        ["部门", "地区", "产品", "数量", "金额", "日期", "销售员"],
        rows, widths=[12, 10, 12, 9, 10, 13, 10])
    add_sheet(
        wb, "备用数据",
        ["部门", "地区", "产品", "数量", "金额", "日期", "销售员"],
        rows[:8], widths=[12, 10, 12, 9, 10, 13, 10])
    save_workbook(wb, os.path.join(folder, "销售明细.xlsx"))


if __name__ == "__main__":
    build_merge_cases()
    build_split_case()
    build_format_case()
    build_extract_replace_case()
    build_convert_case()
    build_template_case()
    build_pivot_case()
    print("\n全部测试数据生成完毕。")


