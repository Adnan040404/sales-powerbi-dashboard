"""
Generates the Power BI project (PBIP / PBIR format) for the sales dashboard:

    Sales Performance Dashboard.pbip
    Sales Performance Dashboard.SemanticModel/   star schema, relationships, DAX measures (TMDL)
    Sales Performance Dashboard.Report/          2 pages of visuals (PBIR) + custom theme

Open the .pbip in Power BI Desktop. The model reads the CSVs in ./data through a
`DataFolder` parameter (Home > Transform data > Edit parameters) so the project
also works after being moved.

    python export_data.py      # refresh data/*.csv from the ETL warehouse
    python build_project.py    # regenerate the project files
"""

import json
import os
import shutil
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "Sales Performance Dashboard"
MODEL_DIR = os.path.join(HERE, f"{NAME}.SemanticModel")
REPORT_DIR = os.path.join(HERE, f"{NAME}.Report")
DATA_DIR = os.path.join(HERE, "data") + os.sep

NAVY, BLUE, GREEN, ORANGE, GOLD, PURPLE = "#1F3864", "#2F5597", "#70AD47", "#ED7D31", "#FFC000", "#9E6BD1"
CANVAS, WHITE, GRID, TEXT_MUTED = "#F3F6FA", "#FFFFFF", "#D9DEE7", "#595959"


def guid(seed):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"sales-dashboard/{seed}"))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def write_json(path, obj):
    write(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


# =====================================================================
#  SEMANTIC MODEL (TMDL)
# =====================================================================
T = "\t"


def m_source(csv, ncols, types):
    type_list = ", ".join(f'{{"{c}", {t}}}' for c, t in types)
    return (f'{T*4}let\n'
            f'{T*5}Source = Csv.Document(File.Contents(DataFolder & "{csv}"), [Delimiter=",", Columns={ncols}, Encoding=65001, QuoteStyle=QuoteStyle.Csv]),\n'
            f'{T*5}Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),\n'
            f'{T*5}Typed = Table.TransformColumnTypes(Promoted, {{{type_list}}}, "en-US")\n'
            f'{T*4}in\n'
            f'{T*5}Typed')


DTYPE = {"text": "string", "date": "dateTime", "int": "int64", "money": "decimal",
         "num": "double", "bool": "boolean"}
MTYPE = {"text": "type text", "date": "type date", "int": "Int64.Type",
         "money": "Currency.Type", "num": "type number", "bool": "type logical"}


def column(table, name, kind, fmt=None, summarize="none", extra=()):
    lines = [f"{T}column {name}", f"{T*2}dataType: {DTYPE[kind]}"]
    if fmt:
        lines.append(f"{T*2}formatString: {fmt}")
    lines += [f"{T*2}lineageTag: {guid(f'{table}.{name}')}",
              f"{T*2}summarizeBy: {summarize}"]
    lines += [f"{T*2}{e}" for e in extra]
    lines.append(f"{T*2}sourceColumn: {name}")
    lines += ["", f"{T*2}annotation SummarizationSetBy = Automatic"]
    if kind == "date":
        lines.append(f"{T*2}annotation UnderlyingDateTimeDataType = Date")
    return "\n".join(lines) + "\n"


def table_tmdl(table, csv, cols, extra_table_props=()):
    out = [f"table {table}", f"{T}lineageTag: {guid(table)}"]
    out += [f"{T}{p}" for p in extra_table_props]
    out.append("")
    for c in cols:
        out.append(column(table, *c[:3], **(c[3] if len(c) > 3 else {})))
    types = [(c[0], MTYPE[c[1]]) for c in cols]
    out.append(f"{T}partition {table} = m\n{T*2}mode: import\n{T*2}source =\n"
               f"{m_source(csv, len(cols), types)}\n")
    out.append(f"{T}annotation PBI_ResultType = Table\n")
    return "\n".join(out)


MEASURES = [
    ("Total Revenue", "SUM(fact_sales[revenue])", "\\$#,0", "Revenue after discounts."),
    ("Orders", "COUNTROWS(fact_sales)", "#,0", "Number of order lines."),
    ("Units Sold", "SUM(fact_sales[quantity])", "#,0", None),
    ("Avg Order Value", "DIVIDE([Total Revenue], [Orders])", "\\$#,0.00", None),
    ("Gross Revenue", "SUMX(fact_sales, fact_sales[quantity] * fact_sales[unit_price])", "\\$#,0",
     "Revenue before discounts."),
    ("Discounts Given", "[Gross Revenue] - [Total Revenue]", "\\$#,0", None),
    ("Discount Rate", "DIVIDE([Discounts Given], [Gross Revenue])", "0.0%", None),
    ("Revenue Prior Month", "CALCULATE([Total Revenue], DATEADD(dim_date[Date], -1, MONTH))",
     "\\$#,0", "Revenue in the previous calendar month (use with a month on rows)."),
    ("Revenue MoM %", "DIVIDE([Total Revenue] - [Revenue Prior Month], [Revenue Prior Month])",
     "+0.0%;-0.0%;0.0%", "Month-over-month growth."),
    ("Revenue YTD", "TOTALYTD([Total Revenue], dim_date[Date])", "\\$#,0", None),
    ("Revenue Share %", "DIVIDE([Total Revenue], CALCULATE([Total Revenue], ALLSELECTED()))",
     "0.0%", "Share of revenue within the current slicer selection."),
    ("Active Customers",
     'CALCULATE(DISTINCTCOUNT(fact_sales[customer]), fact_sales[customer] <> "Unknown")',
     "#,0", "Distinct named customers."),
    ("Revenue per Customer", "DIVIDE([Total Revenue], [Active Customers])", "\\$#,0.00", None),
    ("Online Share %",
     'DIVIDE(CALCULATE([Total Revenue], fact_sales[channel] = "Online"), [Total Revenue])',
     "0.0%", None),
]


def measures_table():
    out = [f"table _Measures", f"{T}lineageTag: {guid('_Measures')}", ""]
    for name, dax, fmt, desc in MEASURES:
        q = f"'{name}'" if " " in name or "%" in name else name
        if desc:
            out.append(f"{T}/// {desc}")
        out += [f"{T}measure {q} = {dax}", f"{T*2}formatString: {fmt}",
                f"{T*2}lineageTag: {guid('measure.' + name)}", ""]
    out += [f"{T}column Placeholder", f"{T*2}isHidden", f"{T*2}dataType: string",
            f"{T*2}lineageTag: {guid('_Measures.Placeholder')}", f"{T*2}summarizeBy: none",
            f"{T*2}sourceColumn: Placeholder", "",
            f"{T*2}annotation SummarizationSetBy = Automatic", "",
            f"{T}partition _Measures = m", f"{T*2}mode: import", f"{T*2}source =",
            f"{T*4}let", f"{T*5}Source = #table(type table [Placeholder = text], {{}})",
            f"{T*4}in", f"{T*5}Source", "",
            f"{T}annotation PBI_ResultType = Table", ""]
    return "\n".join(out)


def build_model():
    if os.path.isdir(MODEL_DIR):
        shutil.rmtree(MODEL_DIR)
    d = os.path.join(MODEL_DIR, "definition")
    write_json(os.path.join(MODEL_DIR, "definition.pbism"), {"version": "4.0", "settings": {}})
    write(os.path.join(d, "database.tmdl"), "database\n\tcompatibilityLevel: 1600\n")
    write(os.path.join(d, "model.tmdl"),
          "model Model\n\tculture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
          "\tdiscourageImplicitMeasures\n\tsourceQueryCulture: en-US\n\n"
          'annotation PBI_QueryOrder = ["DataFolder","fact_sales","dim_date","dim_product"]\n\n'
          "ref table fact_sales\nref table dim_date\nref table dim_product\nref table _Measures\n\n"
          "ref expression DataFolder\n")
    write(os.path.join(d, "expressions.tmdl"),
          f'expression DataFolder = "{DATA_DIR}" meta [IsParameterQuery=true, Type="Text", '
          f'IsParameterQueryRequired=true]\n{T}lineageTag: {guid("DataFolder")}\n'
          f'\n{T}annotation PBI_ResultType = Text\n')

    write(os.path.join(d, "tables", "fact_sales.tmdl"), table_tmdl("fact_sales", "fact_sales.csv", [
        ("order_id", "text"), ("order_date", "date", "Long Date"), ("customer", "text"),
        ("product", "text"), ("channel", "text"),
        ("quantity", "int", "0"), ("unit_price", "money", "\\$#,0.00;(\\$#,0.00);\\$#,0.00"),
        ("discount", "num", "0%"), ("revenue", "money", "\\$#,0.00;(\\$#,0.00);\\$#,0.00")]))
    write(os.path.join(d, "tables", "dim_date.tmdl"), table_tmdl("dim_date", "dim_date.csv", [
        ("Date", "date", "dd mmm yyyy", {"extra": ["isKey"]}), ("Year", "int", "0"),
        ("Quarter", "text"), ("MonthNumber", "int", "0"),
        ("Month", "text", None, {"extra": ["sortByColumn: MonthNumber"]}),
        ("MonthYear", "text", None, {"extra": ["sortByColumn: MonthStart"]}),
        ("MonthStart", "date", "mmm yyyy"), ("WeekdayNumber", "int", "0"),
        ("Weekday", "text", None, {"extra": ["sortByColumn: WeekdayNumber"]}),
        ("IsWeekend", "bool")], extra_table_props=["dataCategory: Time"]))
    write(os.path.join(d, "tables", "dim_product.tmdl"), table_tmdl("dim_product", "dim_product.csv", [
        ("product", "text"), ("category", "text")]))
    write(os.path.join(d, "tables", "_Measures.tmdl"), measures_table())
    write(os.path.join(d, "relationships.tmdl"),
          f"relationship {guid('rel.date')}\n{T}fromColumn: fact_sales.order_date\n"
          f"{T}toColumn: dim_date.Date\n\n"
          f"relationship {guid('rel.product')}\n{T}fromColumn: fact_sales.product\n"
          f"{T}toColumn: dim_product.product\n")


# =====================================================================
#  REPORT (PBIR)
# =====================================================================
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
VER = {"visual": "2.2.0", "page": "2.0.0", "report": "3.0.0"}


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def s(text):
    return lit("'" + text.replace("'", "''") + "'")


def num(n):
    return lit(f"{n}D")


def flag(b):
    return lit("true" if b else "false")


def color(hexv):
    return {"solid": {"color": s(hexv)}}


def col_field(entity, prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def measure_field(prop):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": "_Measures"}}, "Property": prop}}


def proj(field, entity=None):
    kind = "Column" if "Column" in field else "Measure"
    ent = field[kind]["Expression"]["SourceRef"]["Entity"]
    prop = field[kind]["Property"]
    return {"field": field, "queryRef": f"{ent}.{prop}", "nativeQueryRef": prop}


def query(roles, sort=None):
    q = {"queryState": {role: {"projections": [proj(f) for f in fields]}
                        for role, fields in roles.items()}}
    if sort:
        q["sortDefinition"] = {"sort": [{"field": f, "direction": d} for f, d in sort],
                               "isDefaultSort": True}
    return q


def container(title=None, fill=WHITE, border=True, title_size=11, title_color=NAVY):
    c = {
        "background": [{"properties": {"show": flag(True), "color": color(fill),
                                       "transparency": num(0)}}],
        "border": [{"properties": {"show": flag(border), "color": color(GRID),
                                   "radius": num(6)}}],
        "dropShadow": [{"properties": {"show": flag(False)}}],
    }
    if title:
        c["title"] = [{"properties": {"show": flag(True), "text": s(title),
                                      "fontColor": color(title_color),
                                      "fontSize": num(title_size), "bold": flag(True),
                                      "alignment": s("left")}}]
    else:
        c["title"] = [{"properties": {"show": flag(False)}}]
    return c


_z = [0]


def visual(name, x, y, w, h, vtype, q=None, objects=None, cont=None):
    _z[0] += 1
    v = {"visualType": vtype, "drillFilterOtherVisuals": True}
    if q:
        v["query"] = q
    if objects:
        v["objects"] = objects
    if cont:
        v["visualContainerObjects"] = cont
    return {
        "$schema": f"{SCHEMA}/visualContainer/{VER['visual']}/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": _z[0] * 100, "height": h, "width": w,
                     "tabOrder": _z[0] * 100},
        "visual": v,
    }


def textbox(name, x, y, w, h, runs, fill=None, align="left"):
    paragraphs = [{"textRuns": runs, "horizontalTextAlignment": align}]
    cont = {"title": [{"properties": {"show": flag(False)}}],
            "border": [{"properties": {"show": flag(False)}}],
            "dropShadow": [{"properties": {"show": flag(False)}}]}
    if fill:
        cont["background"] = [{"properties": {"show": flag(True), "color": color(fill),
                                              "transparency": num(0)}}]
    return visual(name, x, y, w, h, "textbox",
                  objects={"general": [{"properties": {"paragraphs": paragraphs}}]}, cont=cont)


def run(text, size="12pt", bold=False, color_hex="#252423"):
    st = {"fontSize": size, "color": color_hex, "fontFamily": "Segoe UI"}
    if bold:
        st["fontWeight"] = "bold"
    return {"value": text, "textStyle": st}


def slicer(name, x, y, w, h, entity, prop, mode, title):
    return visual(
        name, x, y, w, h, "slicer",
        q=query({"Values": [col_field(entity, prop)]}),
        objects={"data": [{"properties": {"mode": s(mode)}}],
                 "header": [{"properties": {"show": flag(True), "fontColor": color(NAVY),
                                            "bold": flag(True), "textSize": num(10)}}]},
        cont=container(None))


def kpi(name, x, y, w, h, measure_name, title):
    return visual(
        name, x, y, w, h, "card",
        q=query({"Values": [measure_field(measure_name)]}),
        objects={"labels": [{"properties": {"color": color(NAVY), "fontSize": num(26),
                                            "fontFamily": s("Segoe UI Semibold")}}],
                 "categoryLabels": [{"properties": {"show": flag(False)}}]},
        cont=container(title, title_size=10, title_color=TEXT_MUTED))


def data_labels():
    return {"labels": [{"properties": {"show": flag(True), "color": color("#252423"),
                                       "fontSize": num(9)}}],
            "categoryAxis": [{"properties": {"fontSize": num(9)}}],
            "valueAxis": [{"properties": {"show": flag(False)}}]}


def page(name, display, visuals):
    return {"name": name, "display": display, "visuals": visuals}


def overview_page():
    v = [
        textbox("header", 0, 0, 1280, 64,
                [run("Sales Performance Dashboard", "22pt", True, WHITE),
                 run("     Jan - Jun 2026  |  3 sources merged by the ETL pipeline  |  sample data",
                     "11pt", False, "#C9D6EE")], fill=NAVY),
        slicer("slicer_date", 16, 76, 400, 52, "dim_date", "Date", "Between", "Date"),
        slicer("slicer_category", 428, 76, 220, 52, "dim_product", "category", "Dropdown", "Category"),
        slicer("slicer_channel", 660, 76, 220, 52, "fact_sales", "channel", "Dropdown", "Channel"),
        kpi("kpi_revenue", 16, 140, 240, 92, "Total Revenue", "TOTAL REVENUE"),
        kpi("kpi_orders", 268, 140, 240, 92, "Orders", "ORDERS"),
        kpi("kpi_units", 520, 140, 240, 92, "Units Sold", "UNITS SOLD"),
        kpi("kpi_aov", 772, 140, 240, 92, "Avg Order Value", "AVG ORDER VALUE"),
        kpi("kpi_customers", 1024, 140, 240, 92, "Active Customers", "ACTIVE CUSTOMERS"),
        visual("chart_month", 16, 244, 620, 228, "clusteredColumnChart",
               q=query({"Category": [col_field("dim_date", "MonthYear")],
                        "Y": [measure_field("Total Revenue")]}),
               objects=data_labels(), cont=container("Revenue by month")),
        visual("chart_channel", 648, 244, 300, 228, "donutChart",
               q=query({"Category": [col_field("fact_sales", "channel")],
                        "Y": [measure_field("Total Revenue")]}),
               objects={"legend": [{"properties": {"show": flag(True), "position": s("Bottom")}}],
                        "labels": [{"properties": {"show": flag(True), "labelStyle": s("Percent of total")}}]},
               cont=container("Revenue by channel")),
        visual("chart_category", 960, 244, 304, 228, "clusteredBarChart",
               q=query({"Category": [col_field("dim_product", "category")],
                        "Y": [measure_field("Total Revenue")]},
                       sort=[(measure_field("Total Revenue"), "Descending")]),
               objects=data_labels(), cont=container("Revenue by category")),
        visual("chart_product", 16, 484, 620, 224, "clusteredBarChart",
               q=query({"Category": [col_field("fact_sales", "product")],
                        "Y": [measure_field("Total Revenue")]},
                       sort=[(measure_field("Total Revenue"), "Descending")]),
               objects=data_labels(), cont=container("Revenue by product")),
        visual("table_month", 648, 484, 616, 224, "tableEx",
               q=query({"Values": [col_field("dim_date", "MonthYear"),
                                   measure_field("Total Revenue"), measure_field("Orders"),
                                   measure_field("Avg Order Value"), measure_field("Revenue MoM %")]},
                       sort=[(col_field("dim_date", "MonthYear"), "Ascending")]),
               objects={"columnHeaders": [{"properties": {"fontColor": color(WHITE),
                                                          "backColor": color(NAVY),
                                                          "fontSize": num(10)}}],
                        "values": [{"properties": {"fontSize": num(10)}}]},
               cont=container("Monthly performance")),
    ]
    return page("overview", "Overview", v)


def products_page():
    v = [
        textbox("header2", 0, 0, 1280, 64,
                [run("Product & Channel Performance", "22pt", True, WHITE),
                 run("     what sells, where, and when", "11pt", False, "#C9D6EE")], fill=NAVY),
        slicer("slicer_month", 16, 76, 300, 52, "dim_date", "MonthYear", "Dropdown", "Month"),
        slicer("slicer_channel2", 328, 76, 220, 52, "fact_sales", "channel", "Dropdown", "Channel"),
        visual("matrix_products", 16, 140, 760, 568, "pivotTable",
               q=query({"Rows": [col_field("dim_product", "category"),
                                 col_field("fact_sales", "product")],
                        "Values": [measure_field("Units Sold"), measure_field("Total Revenue"),
                                   measure_field("Revenue Share %"), measure_field("Avg Order Value")]}),
               objects={"columnHeaders": [{"properties": {"fontColor": color(WHITE),
                                                          "backColor": color(NAVY),
                                                          "fontSize": num(10)}}],
                        "values": [{"properties": {"fontSize": num(10)}}]},
               cont=container("Category and product breakdown")),
        visual("treemap_category", 788, 140, 476, 280, "treemap",
               q=query({"Group": [col_field("dim_product", "category")],
                        "Values": [measure_field("Total Revenue")]}),
               objects={"labels": [{"properties": {"show": flag(True), "fontSize": num(10)}}]},
               cont=container("Revenue mix by category")),
        visual("chart_weekday", 788, 432, 476, 276, "clusteredColumnChart",
               q=query({"Category": [col_field("dim_date", "Weekday")],
                        "Y": [measure_field("Total Revenue")]}),
               objects=data_labels(), cont=container("Revenue by weekday")),
    ]
    return page("products", "Products & Channels", v)


THEME = {
    "name": "Sales Theme",
    "dataColors": [NAVY, "#2F5597", "#5B9BD5", GREEN, ORANGE, GOLD, PURPLE, "#A5A5A5"],
    "background": WHITE, "foreground": "#252423", "tableAccent": NAVY,
    "good": "#2E7D32", "neutral": GOLD, "bad": "#C62828",
    "maximum": NAVY, "center": "#5B9BD5", "minimum": "#DEEBF7",
    "textClasses": {
        "callout": {"fontSize": 28, "fontFace": "Segoe UI Semibold", "color": NAVY},
        "title": {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": NAVY},
        "header": {"fontSize": 10, "fontFace": "Segoe UI Semibold", "color": NAVY},
        "label": {"fontSize": 9, "fontFace": "Segoe UI", "color": "#252423"},
    },
    "visualStyles": {"*": {"*": {"*": [{"fontFamily": "Segoe UI"}]}}},
}


def build_report():
    if os.path.isdir(REPORT_DIR):
        shutil.rmtree(REPORT_DIR)
    d = os.path.join(REPORT_DIR, "definition")
    write_json(os.path.join(REPORT_DIR, "definition.pbir"),
               {"version": "4.0",
                "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    write_json(os.path.join(d, "version.json"),
               {"$schema": f"{SCHEMA}/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    at_import = dict(VER)
    write_json(os.path.join(d, "report.json"), {
        "$schema": f"{SCHEMA}/report/{VER['report']}/schema.json",
        "themeCollection": {
            "baseTheme": {"name": "CY24SU10", "reportVersionAtImport": at_import,
                          "type": "SharedResources"},
            "customTheme": {"name": "SalesTheme.json", "reportVersionAtImport": at_import,
                            "type": "RegisteredResources"}},
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": "SalesTheme.json", "path": "SalesTheme.json", "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True,
                     "allowChangeFilterTypes": True, "useEnhancedTooltips": True,
                     "useDefaultAggregateDisplayName": True},
    })
    write_json(os.path.join(REPORT_DIR, "StaticResources", "RegisteredResources", "SalesTheme.json"), THEME)

    pages = [overview_page(), products_page()]
    write_json(os.path.join(d, "pages", "pages.json"), {
        "$schema": f"{SCHEMA}/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [p["name"] for p in pages], "activePageName": pages[0]["name"]})
    for p in pages:
        pd_ = os.path.join(d, "pages", p["name"])
        write_json(os.path.join(pd_, "page.json"), {
            "$schema": f"{SCHEMA}/page/{VER['page']}/schema.json",
            "name": p["name"], "displayName": p["display"], "displayOption": "FitToPage",
            "height": 720, "width": 1280,
            "objects": {"background": [{"properties": {"color": color(CANVAS),
                                                       "transparency": num(0)}}]}})
        for vis in p["visuals"]:
            write_json(os.path.join(pd_, "visuals", vis["name"], "visual.json"), vis)


def build_dax_file():
    lines = ["// DAX measures for the Sales Performance Dashboard.",
             "// Create a blank table called _Measures (Home > Enter data), then add each measure",
             "// below with Modeling > New measure. Model needs: fact_sales, dim_date (marked as",
             "// date table, related on order_date), dim_product (related on product).", ""]
    for name, dax, fmt, desc in MEASURES:
        if desc:
            lines.append(f"// {desc}")
        lines.append(f"{name} = {dax}")
        lines.append(f"// format: {fmt.replace(chr(92), '')}")
        lines.append("")
    write(os.path.join(HERE, "powerbi", "measures.dax"), "\n".join(lines))


def build_root():
    write_json(os.path.join(HERE, f"{NAME}.pbip"),
               {"version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                "settings": {"enableAutoRecovery": True}})
    write(os.path.join(HERE, ".gitignore"),
          "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n__pycache__/\n")


if __name__ == "__main__":
    build_model()
    build_report()
    build_dax_file()
    build_root()
    print("Project written to", HERE)
