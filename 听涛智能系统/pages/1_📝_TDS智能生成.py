import streamlit as st
from google import genai
import json
import re
import os
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import io

# ================= 0. 🔑 在这里焊死你的 API Key =================
MY_API_KEY = st.secrets["MY_API_KEY"]

# ================= 1. Word 排版辅助函数 =================
def split_cn_en(text):
    if not text: return ""
    return re.sub(r'([\u4e00-\u9fa5]+)\s+([a-zA-Z].*)', r'\1\n\2', str(text))

def set_cell_background(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)

def format_cell_text(cell, text, is_header=False, is_property_col=False, align_left=False):
    cell.text = "" 
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    if not cell.paragraphs: cell.add_paragraph()
    paragraph = cell.paragraphs[0]
    paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT if align_left else WD_PARAGRAPH_ALIGNMENT.CENTER
    
    processed_text = str(text)
    if len(processed_text) < 12:
        processed_text = processed_text.replace("°C", "℃").replace(" C", " ℃")
        if processed_text.strip() == "C": processed_text = "℃"
    
    display_text = split_cn_en(processed_text) if is_property_col else processed_text
    run = paragraph.add_run(display_text)
    run.font.name = 'Calibri'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    run.font.size = Pt(10)
    if is_header:
        run.font.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)

def remove_row(table, row):
    table._tbl.remove(row._tr)

# ================= 2. 核心排版引擎 =================
def generate_docx(data):
    doc = Document("TDS 模板.docx")
    processed_features = False
    processed_apps = False
    processed_props = False
    processed_guide = False

    for table in doc.tables:
        if len(table.rows) == 0: continue
        table_text = "".join([c.text for r in table.rows for c in r.cells])
        if any(kw in table_text for kw in ["声明", "Disclaimer", "备注"]): continue

        for i, row in enumerate(table.rows):
            cell_text = row.cells[0].text.strip().upper()
            if not processed_features and ("特性" in cell_text or "FEATURES" in cell_text) and "性能" not in cell_text:
                if i + 1 < len(table.rows):
                    items = data.get("Features", [])
                    content = "\n".join([f"• {x}" for x in items]) if items else "无"
                    format_cell_text(table.rows[i+1].cells[0], content, align_left=True)
                    processed_features = True
            
            if not processed_apps and ("推荐使用" in cell_text or "APPLICATIONS" in cell_text or "应用" in cell_text):
                if i + 1 < len(table.rows):
                    items = data.get("Applications", [])
                    content = "\n".join([f"• {x}" for x in items]) if items else "无"
                    format_cell_text(table.rows[i+1].cells[0], content, align_left=True)
                    processed_apps = True

        header_cell = table.rows[0].cells[0].text.strip()
        if not processed_props and any(kw in header_cell for kw in ["性能", "Properties"]) and len(table.rows[0].cells) >= 4:
            processed_props = True
            prop_data = {item.get("Property", "").strip(): item for item in data.get("TypicalProperties", [])}
            found_keys = set()
            to_delete = []

            for r in table.rows[1:]:
                tmp_name = r.cells[0].text.strip()
                match = None
                for k, v in prop_data.items():
                    if tmp_name in k or k in tmp_name:
                        match = v
                        found_keys.add(k)
                        break
                if match:
                    r.cells[0].text, r.cells[1].text = match.get("Property",""), match.get("TestMethod","")
                    r.cells[2].text, r.cells[3].text = match.get("Value",""), match.get("Unit","")
                else:
                    to_delete.append(r)
            
            for r in to_delete: remove_row(table, r)
            for k, v in prop_data.items():
                if k not in found_keys:
                    nr = table.add_row()
                    nr.cells[0].text, nr.cells[1].text = v.get("Property",""), v.get("TestMethod","")
                    nr.cells[2].text, nr.cells[3].text = v.get("Value",""), v.get("Unit","")

            for i, row in enumerate(table.rows):
                for j, cell in enumerate(row.cells):
                    if i == 0:
                        set_cell_background(cell, "1F497D")
                        format_cell_text(cell, cell.text.strip(), is_header=True, is_property_col=False)
                    else:
                        format_cell_text(cell, cell.text.strip(), is_property_col=(j==0))
                        set_cell_background(cell, "F2F2F2" if i % 2 == 0 else "FFFFFF")

        elif not processed_guide and any(kw in header_cell for kw in ["加工", "Melt", "熔体"]):
            processed_guide = True
            for r in table.rows: remove_row(table, r)
            guide = data.get("ProcessingGuide", {})
            mapping = {
                "MeltTemp": "熔体温度 Melt Temp", "MoldTemp": "模温 Mold Temp",
                "BarrelZoneTemp": "料筒温度 Barrel Zone Temp", "InjectionSpeed": "注塑速度 Injection Speed",
                "BackPressure": "背压 Back Pressure", "DryingCondition": "干燥条件 Drying Condition",
                "ProcessingTemp": "加工上限温度 Processing Temp"
            }
            idx = 0
            for k, zh in mapping.items():
                val = guide.get(k, "")
                if val and val != "无":
                    nr = table.add_row()
                    for c_idx, cell in enumerate(nr.cells):
                        is_label = (c_idx == 0)
                        format_cell_text(cell, zh if is_label else val, is_property_col=False, align_left=is_label)
                        set_cell_background(cell, "F2F2F2" if idx % 2 == 0 else "FFFFFF")
                    idx += 1

    target_stream = io.BytesIO()
    doc.save(target_stream)
    return target_stream.getvalue()

# ================= 3. 网页界面与 AI 通信 =================
st.set_page_config(page_title="听涛 TDS 智能生成", page_icon="📝")
st.title("🚀 听涛新材料 - 全能 TDS 提取系统")
st.markdown("上传原厂资料，**支持图片、PDF、Word、Excel**，AI 将自动阅读并生成标准 Word 文档。")

uploaded_file = st.file_uploader("📥 请上传原厂物料文件", type=['png', 'jpg', 'jpeg', 'pdf', 'docx', 'xlsx'])

if st.button("✨ 一键识别并生成 TDS", type="primary"):
    if MY_API_KEY == "在这里填入你的真实API_KEY":
        st.error("❌ 哎呀，你忘记在代码里填入真实的 API Key 了！请打开 web_tds.py 修改第 15 行。")
    elif not uploaded_file:
        st.error("❌ 请先上传文件哦！")
    else:
        try:
            with st.spinner(f"🧠 正在上传解析【{uploaded_file.name}】，AI 阅读可能需要几十秒..."):
                client = genai.Client(api_key=MY_API_KEY)
                
                # 修复中文名报错：强制给临时文件穿上“纯英文马甲”
                file_ext = os.path.splitext(uploaded_file.name)[1]
                temp_file_path = f"temp_ai_upload_file{file_ext}"
                
                with open(temp_file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                gemini_file = client.files.upload(file=temp_file_path)

                # ==========================================
                # 终极版 Prompt：特性和应用也强制输出中英双语
                # ==========================================
                prompt = """
                你是一个专业的数据提取员兼材料学翻译专家。请仔细阅读我上传的文件资料，提取其中的塑料物性表数据，并严格输出为以下的 JSON 格式。
                
                【💡 核心提取与翻译规则（非常重要）】：
                1. 对于 `TypicalProperties` 中的 `Property` 字段：必须强制输出【中文 + 空格 + 英文】的对照格式（例如："拉伸强度 Tensile Strength"）。
                2. 对于 `Features` (特性) 和 `Applications` (应用)：无论原文件是纯中文还是纯英文，你也必须强制输出【中文 + 空格 + 英文】的对照格式（例如："优异的耐热性 Excellent heat resistance"）。原文件缺失的语言请你自动翻译并补齐。
                3. 不要回复任何其他说明文字，也不要包含 ```json 标签。
                
                输出格式模板：
                {
                  "ProductName": "提取物料名称",
                  "Features": ["优异的耐热性 Excellent heat resistance", "高流动性 High flowability"],
                  "Applications": ["汽车零部件 Automotive parts", "电子电器外壳 Electrical enclosures"],
                  "TypicalProperties": [
                    {"Property": "拉伸强度 Tensile Strength", "TestMethod": "ASTM D638", "Value": "60", "Unit": "MPa"}
                  ],
                  "ProcessingGuide": {
                    "MeltTemp": "240-270 °C",
                    "MoldTemp": "60-80 °C"
                  }
                }
                """
                
                response = client.models.generate_content(
                    model='gemini-3-flash-preview',
                    contents=[prompt, gemini_file]
                )
                
                os.remove(temp_file_path)
                try:
                    client.files.delete(name=gemini_file.name)
                except:
                    pass
                
                result_text = response.text
                if "```json" in result_text:
                    result_text = result_text.split("```json")[1].split("```")[0].strip()
                elif "```" in result_text:
                    result_text = result_text.split("```")[1].split("```")[0].strip()
                    
                data = json.loads(result_text)
                
            with st.spinner("📝 数据提取成功！正在生成完美排版的文档..."):
                docx_bytes = generate_docx(data)
                
            st.success("🎉 TDS 生成完毕！请点击下方按钮下载。")
            safe_name = str(data.get('ProductName', '新物料')).replace('/', '_')
            st.download_button(
                label="📥 下载 Word 文档",
                data=docx_bytes,
                file_name=f"听涛TDS_{safe_name}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            
        except Exception as e:
            st.error(f"❌ 运行过程中出现错误：{e}")
            if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                os.remove(temp_file_path)