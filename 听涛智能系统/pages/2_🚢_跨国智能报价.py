import streamlit as st
import requests
from datetime import datetime

# ==========================================
# 1. 页面配置与自适应布局设置
# ==========================================
st.set_page_config(page_title="跨国智能报价系统 (厦门-胡志明)", page_icon="🚢", layout="centered")

# ==========================================
# 2. 核心数据与装载逻辑 (已精准匹配实际业务数据)
# ==========================================
CONTAINER_TONNAGE = {
    "20GP": {"散包 (直接装)": 25.0, "托盘装 (1吨/托)": 18.0},
    "40GP": {"散包 (直接装)": 27.0, "托盘装 (1吨/托)": 27.0},
    "40HQ": {"散包 (直接装)": 27.0, "托盘装 (1吨/托)": 27.0}
}

# ==========================================
# 3. 汇率自动抓取函数
# ==========================================
@st.cache_data(ttl=3600) # 缓存1小时，避免频繁请求
def fetch_exchange_rates():
    try:
        url = "https://api.exchangerate-api.com/v4/latest/CNY"
        response = requests.get(url, timeout=5)
        data = response.json()
        return {
            "CNY_USD": data["rates"]["USD"],
            "CNY_VND": data["rates"]["VND"]
        }
    except Exception as e:
        st.warning("⚠️ 实时汇率抓取失败，已自动切换至系统保底汇率。")
        return {"CNY_USD": 0.138, "CNY_VND": 3450}

rates = fetch_exchange_rates()

# ==========================================
# 4. 移动端 UI 界面构建
# ==========================================
st.header("🚢 智能报价系统")
st.caption(f"今日汇率更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# --- 汇率微调面板 ---
with st.expander("💱 当日汇率 (可手动微调)", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        cny_usd_rate = st.number_input("CNY/USD 汇率", value=float(rates["CNY_USD"]), format="%.4f")
    with col2:
        cny_vnd_rate = st.number_input("CNY/VND 汇率", value=float(rates["CNY_VND"]), format="%.0f")

st.divider()

# --- 基础产品信息 ---
st.subheader("1. 采购与利润基数")
col1, col2 = st.columns(2)
with col1:
    material = st.selectbox("材料品类", ["PC/ASA", "PBT", "MXD6", "其他工程塑料"])
    price_rmb = st.number_input("国内含税采购单价 (RMB/吨)", value=15000, step=500)
with col2:
    profit_margin = st.number_input("目标利润率 (%)", value=5.0, step=1.0)
    tax_rebate = st.checkbox("享受 13% 退税", value=True)

# 计算真实成本基数
base_cost_rmb = price_rmb / 1.13 if tax_rebate else price_rmb

st.divider()

# --- 物流模式选择与动态费用 ---
st.subheader("2. 厦门至胡志明物流参数")
logistics_mode = st.radio("物流模式", ["整柜 (FCL)", "散货 (LCL)"], horizontal=True)

tonnage = 0.0
total_domestic_fee_rmb = 0.0
total_sea_freight_usd = 0.0

if logistics_mode == "整柜 (FCL)":
    col1, col2 = st.columns(2)
    with col1:
        container_type = st.selectbox("选择柜型", ["20GP", "40GP", "40HQ"])
    with col2:
        packing_type = st.selectbox("装载方式", ["散包 (直接装)", "托盘装 (1吨/托)"])
    
    tonnage = CONTAINER_TONNAGE[container_type][packing_type]
    st.info(f"💡 系统已匹配: **{container_type} {packing_type} 单柜装载量 {tonnage} 吨**")
    
    total_domestic_fee_rmb = st.number_input("国内港杂拖车费 (RMB/柜)", value=1500, step=100)
    
    st.markdown("🚨 **动态海运费用**")
    total_sea_freight_usd = st.number_input("海运费 (USD/柜) - 每次按实填", value=200, step=10)

else:
    # --- 散货 (LCL) 智能阶梯计价 ---
    tonnage = st.number_input("散货总计费发货吨数", value=3.0, step=0.5)
    
    st.markdown("🚨 **固定港杂费 (含报关/文件/CFS场站/THC等)**")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        fixed_domestic_rmb = st.number_input("按票固定港杂费 (RMB/票)", value=1120, step=50) 
    with col_f2:
        fixed_port_usd = st.number_input("按票固定美元杂费 (USD/票)", value=15, step=5)
        
    st.markdown("🚨 **纯海运费与拖车**")
    net_usd_per_ton = st.number_input("纯海运单价 (O/F, USD/吨, 可填负数)", value=-5, step=1)
    
    # 拖车费智能阶梯匹配 (同安 - 象屿)
    trucking_rmb = 0
    if tonnage <= 1.0:
        trucking_rmb = 350
    elif tonnage <= 2.0:
        trucking_rmb = 400
    elif tonnage <= 3.0:
        trucking_rmb = 500
    elif tonnage <= 4.0:
        trucking_rmb = 550
    elif tonnage <= 5.0:
        trucking_rmb = 600
    elif tonnage <= 10.0:
        trucking_rmb = 900
    else:
        trucking_rmb = 900 + (tonnage - 10) * 80 
        
    total_domestic_fee_rmb = fixed_domestic_rmb + trucking_rmb
    total_sea_freight_usd = fixed_port_usd + (net_usd_per_ton * tonnage)
    
    st.info(f"💡 **系统已匹配散货阶梯与固定计价：**\n\n"
            f"1️⃣ 固定港杂费: **{fixed_domestic_rmb} RMB + ${fixed_port_usd} USD**\n"
            f"2️⃣ 阶梯拖车费: **{trucking_rmb} RMB** (匹配 {tonnage}吨档位)\n"
            f"3️⃣ 纯海运费合计: **${net_usd_per_ton * tonnage} USD**")

st.divider()

# --- 目的港及清关派送 ---
st.subheader("3. 越南目的港清关及派送 (DDP所需)")
with st.expander("点击展开填写清关与派送参数", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        vn_import_tax = st.number_input("越南进口关税率 (%)", value=0.0, step=1.0)
    with col2:
        vn_vat = st.number_input("越南增值税率 (VAT %)", value=8.0, step=1.0)
    
    vn_port_misc_vnd = st.number_input("目的港杂费及清关代理 (VND/票)", value=3000000, step=500000)
    
    st.markdown("🚨 **动态派送费用**")
    if logistics_mode == "整柜 (FCL)":
        vn_delivery_vnd = st.number_input("胡志明内陆拖车费 (VND/柜)", value=2500000, step=100000)
    else:
        vn_delivery_vnd = st.number_input("胡志明散货派送费 (VND/票)", value=1000000, step=100000)

st.divider()

# ==========================================
# 5. 最终报价计算逻辑
# ==========================================
if st.button("🚀 一键生成报价", use_container_width=True, type="primary"):
    if tonnage <= 0:
        st.error("吨数不能为0，请检查物流参数！")
    else:
        # --- 计算 A. CIF 报价 ---
        goods_cost_usd = (base_cost_rmb * tonnage) * cny_usd_rate
        domestic_fee_usd = total_domestic_fee_rmb * cny_usd_rate
        total_cif_cost_usd = goods_cost_usd + domestic_fee_usd + total_sea_freight_usd
        
        cif_quote_per_ton_usd = (total_cif_cost_usd / tonnage) * (1 + profit_margin / 100)

        # --- 计算 B. DDP 报价 ---
        usd_vnd_rate = cny_vnd_rate / cny_usd_rate
        total_cif_vnd = total_cif_cost_usd * usd_vnd_rate
        
        duty_vnd = total_cif_vnd * (vn_import_tax / 100)
        vat_vnd = (total_cif_vnd + duty_vnd) * (vn_vat / 100)
        
        total_ddp_cost_vnd = total_cif_vnd + duty_vnd + vat_vnd + vn_port_misc_vnd + vn_delivery_vnd
        
        total_kg = tonnage * 1000
        ddp_quote_per_kg_vnd = (total_ddp_cost_vnd / total_kg) * (1 + profit_margin / 100)

        # --- 展示结果 ---
        st.success("计算完成！")
        
        st.markdown("### 方案 A: CIF 胡志明")
        st.metric(label="CIF 报价 (美金 / 吨)", value=f"${cif_quote_per_ton_usd:,.2f}")
        
        st.markdown("### 方案 B: DDP 越南客户工厂")
        st.metric(label="DDP 报价 (越南盾 / 公斤)", value=f"₫{ddp_quote_per_kg_vnd:,.0f}")