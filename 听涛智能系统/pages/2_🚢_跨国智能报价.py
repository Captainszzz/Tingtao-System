import streamlit as st
import requests
from datetime import datetime

# ==========================================
# 1. 全局配置与数据字典 (基于真实账单)
# ==========================================
st.set_page_config(page_title="听涛智能报价系统", page_icon="🌊", layout="wide")

POL_FEES_USD = {
    "fixed_per_bl": 70 + 30 + 55 + 20 + 25 + 55,  # 文件/报关/提单/EDI/封条/操作 = 255 USD
    "20GP": {"THC": 105, "Booking": 20, "Trucking": 105}, # 230 USD
    "40GP": {"THC": 165, "Booking": 20, "Trucking": 210}, # 395 USD
    "40HQ": {"THC": 165, "Booking": 20, "Trucking": 210}  # 395 USD
}

POD_FEES_USD = {
    "fixed_per_do": 48 + 40, # D/O + 操作费 = 88 USD
    "20GP": {"THC": 140, "CIC": 65, "EMS": 25, "Cleaning": 15}, # 245 USD
    "40GP": {"THC": 222, "CIC": 130, "EMS": 35, "Cleaning": 25}, # 412 USD
    "40HQ": {"THC": 222, "CIC": 130, "EMS": 35, "Cleaning": 25}  # 412 USD
}

WAREHOUSE_RATES = {
    "storage_per_ton_day": 5200,      
    "handling_pallet": 68000,         
    "handling_loose": 105000          
}

# ==========================================
# 2. 汇率引擎与风控参数
# ==========================================
@st.cache_data(ttl=3600)
def fetch_exchange_rates():
    try:
        data = requests.get("https://api.exchangerate-api.com/v4/latest/CNY", timeout=5).json()
        return {"CNY_USD": data["rates"]["USD"], "CNY_VND": data["rates"]["VND"]}
    except:
        return {"CNY_USD": 0.1385, "CNY_VND": 3460}

rates = fetch_exchange_rates()

with st.sidebar:
    st.header("⚙️ 汇率与风控引擎")
    exchange_buffer = st.slider("汇率安全垫 (%)", 0.0, 5.0, 1.5) / 100
    effective_usd_rate = rates["CNY_USD"] * (1 - exchange_buffer)
    effective_vnd_rate = rates["CNY_VND"] * (1 - exchange_buffer)
    st.info(f"**实际结算汇率:**\n\n1 CNY = {effective_usd_rate:.4f} USD\n\n1 CNY = {effective_vnd_rate:.0f} VND")
    
    st.divider()
    st.markdown("### 商业利润")
    profit_margin = st.number_input("目标纯利润率 (%)", value=5.0)
    loss_rate = st.number_input("破损/隐形成本预留 (%)", value=0.5)

# ==========================================
# 3. 核心计算界面
# ==========================================
st.title("🌊 听涛智能报价系统")

# --- 模块 A: 采购与装载 ---
with st.expander("📦 A. 货物基础参数 (展开/折叠)", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        price_rmb_tax = st.number_input("含税采购价 (RMB/吨)", value=15000, step=500)
    with c2:
        rebate_rate = st.number_input("出口退税率 (%)", value=13)
    with c3:
        packing = st.selectbox("包装方式", ["托盘装 (1吨/托)", "散包 (25kg/包)"])
    with c4:
        tonnage = st.number_input("总重量 (吨)", value=25.0)

    # 实际采购成本 (扣除退税)
    cost_per_ton_rmb = price_rmb_tax - (price_rmb_tax / 1.13 * (rebate_rate/100))
    
    # 资金成本引擎
    st.markdown("### 💰 资金与账期成本设定")
    cc1, cc2 = st.columns([2, 2])
    with cc1:
        payment_terms = st.selectbox(
            "客户账期 / 资金占用时间", 
            [
                "0个月 - 现款现货 (仅 0.5% 基础资金成本)",
                "1个月 - OA/远期 (基础 0.5% + 延期 0.8% = 1.3%)",
                "2个月 - OA/远期 (基础 0.5% + 延期 1.6% = 2.1%)",
                "3个月 - OA/远期 (基础 0.5% + 延期 2.4% = 2.9%)"
            ]
        )
    
    months = int(payment_terms[0])
    capital_rate = 0.5 + (months * 0.8)
    
    total_capital_cost_rmb = (price_rmb_tax * tonnage) * (capital_rate / 100)
    total_capital_cost_usd = total_capital_cost_rmb * effective_usd_rate
    
    with cc2:
        st.warning(f"💡 当前综合资金成本率: **{capital_rate:.1f}%**\n\n"
                   f"💴 预计单票垫资利息: **¥{total_capital_cost_rmb:,.0f}** (约 **${total_capital_cost_usd:,.0f}**)")

# --- 模块 B: 海运及中国起运港 ---
st.subheader("B. 跨国海运与 POL 费用 (China EXW/FOB)")
mode = st.radio("运输模式", ["整柜 (FCL)", "散货 (LCL)"], horizontal=True)

total_pol_usd = 0.0
ocean_freight_usd = 0.0

if mode == "整柜 (FCL)":
    l1, l2, l3 = st.columns(3)
    with l1:
        ctype = st.selectbox("选择柜型", ["20GP", "40GP", "40HQ"])
    with l2:
        ocean_freight_usd = st.number_input("海运费 O/F (USD/柜)", value=850.0, step=50.0)
    with l3:
        has_inspect = st.checkbox("需海关查验 (操作费 +$60)", value=False)
    
    pol_fixed = POL_FEES_USD["fixed_per_bl"]
    pol_variable = sum(POL_FEES_USD[ctype].values())
    total_pol_usd = pol_fixed + pol_variable + (60 if has_inspect else 0)

else:
    l1, l2, l3 = st.columns(3)
    with l1:
        cbm = st.number_input("总体积 (CBM)", value=tonnage * 1.3)
    with l2:
        lcl_ocean_usd = st.number_input("散货海运单价 (USD/RT)", value=15.0)
    with l3:
        pol_lcl_fixed_usd = st.number_input("散货起运港杂费 (USD/票)", value=150.0)
    
    rt = max(tonnage, cbm)
    ocean_freight_usd = lcl_ocean_usd * rt
    total_pol_usd = pol_lcl_fixed_usd

# --- 模块 C: 越南目的港与仓配 ---
st.subheader("C. 越南本地费用与仓储 (Vietnam POD & Warehousing)")

if mode == "整柜 (FCL)":
    pod_fixed = POD_FEES_USD["fixed_per_do"]
    pod_variable = sum(POD_FEES_USD[ctype].values())
    pod_local_fees_usd = pod_fixed + pod_variable
else:
    pod_local_fees_usd = st.number_input("散货目的港杂费 (USD/票)", value=80.0)

pod_fees_vnd_no_tax = pod_local_fees_usd * (effective_vnd_rate / effective_usd_rate)
pod_fees_vat_vnd = pod_fees_vnd_no_tax * 0.08

d1, d2, d3, d4 = st.columns(4)
with d1:
    import_tax = st.number_input("进口关税 (%)", value=0.0)
with d2:
    import_vat = st.number_input("货物进口增值税 (%)", value=8.0)
with d3:
    customs_tip_vnd = st.number_input("海关查验/小费 (VND)", value=1000000, step=500000)
with d4:
    # 🌟 修改点 1：变更为 港口-仓库拖车费用 (USD)
    delivery_truck_usd = st.number_input("港口-仓库拖车费用 (USD)", value=107.0)

# 仓储与末端派送模块
st.markdown("🏢 **海外仓配与末端派送**")
w1, w2, w3 = st.columns(3)
with w1:
    needs_warehousing = st.checkbox("✔️ 货物需进入本地仓储转运", value=True)
with w2:
    storage_days = st.number_input("预计存储天数", value=7, min_value=0) if needs_warehousing else 0
with w3:
    # 🌟 修改点 2：新增越南本土运费（仓库-客户），使用 VND 录入
    vn_delivery_to_client_vnd = st.number_input("越南本土运费 (仓库-客户, VND)", value=2000000, step=500000)

warehouse_total_vnd = 0
if needs_warehousing:
    storage_fee_vnd = WAREHOUSE_RATES["storage_per_ton_day"] * tonnage * storage_days
    handling_rate = WAREHOUSE_RATES["handling_pallet"] if "托盘" in packing else WAREHOUSE_RATES["handling_loose"]
    handling_fee_vnd = handling_rate * tonnage * 2 
    warehouse_total_vnd = storage_fee_vnd + handling_fee_vnd
    st.caption(f"*(明细: 仓储费 ₫{storage_fee_vnd:,.0f} + 双边装卸费 ₫{handling_fee_vnd:,.0f})*")

st.divider()

# ==========================================
# 4. 终极计算引擎
# ==========================================
if st.button("🚀 一键生成精准报价表", use_container_width=True, type="primary"):
    
    # 1. 货值计算 (退税后真实成本)
    total_goods_cost_usd = (cost_per_ton_rmb * tonnage) * effective_usd_rate
    
    # 2. CIF 计算 (货值 + 中国杂费 + 海运费 + 资金成本) / 扣减保险
    insurance_rate = 0.0008 
    total_cif_usd = (total_goods_cost_usd + total_pol_usd + ocean_freight_usd + total_capital_cost_usd) / (1 - (insurance_rate * 1.1))
    
    # 利润加成
    cif_quote_total_usd = total_cif_usd * (1 + profit_margin/100) * (1 + loss_rate/100)
    cif_quote_per_ton = cif_quote_total_usd / tonnage

    # 3. DDP 费用计算 (转换为 VND)
    usd_to_vnd = effective_vnd_rate / effective_usd_rate
    cif_vnd = total_cif_usd * usd_to_vnd
    
    duty_vnd = cif_vnd * (import_tax / 100)
    vat_on_goods_vnd = (cif_vnd + duty_vnd) * (import_vat / 100)
    
    # 头程本地拖车 (港口到仓库)
    local_delivery_port_to_wh_vnd = delivery_truck_usd * usd_to_vnd
    
    # 🌟 修改点 3：目的港本地成本汇总 加入了 vn_delivery_to_client_vnd (仓库到客户)
    total_pod_costs_vnd = pod_fees_vnd_no_tax + pod_fees_vat_vnd + customs_tip_vnd + warehouse_total_vnd + local_delivery_port_to_wh_vnd + vn_delivery_to_client_vnd
    
    # 最终 DDP
    total_ddp_cost_vnd = cif_vnd + duty_vnd + vat_on_goods_vnd + total_pod_costs_vnd
    ddp_quote_total_vnd = total_ddp_cost_vnd * (1 + profit_margin/100) * (1 + loss_rate/100)
    ddp_quote_per_kg = ddp_quote_total_vnd / (tonnage * 1000)

    # 结果展示
    st.success("✅ 数据核算完毕！各项本地费用及垫资利息已计入总成本。")
    
    res1, res2 = st.columns(2)
    with res1:
        st.info("### 方案 A: CIF 胡志明 (USD/吨)")
        st.metric(label="CIF 报价单价", value=f"${cif_quote_per_ton:,.2f}")
        st.markdown(f"**总价:** `${cif_quote_total_usd:,.2f}`")
        
    with res2:
        st.success("### 方案 B: DDP 含本地派送 (VND/KG)")
        st.metric(label="DDP 报价单价", value=f"₫ {ddp_quote_per_kg:,.0f}")
        st.markdown(f"**总价:** `₫ {ddp_quote_total_vnd:,.0f}`")
        
    st.markdown("---")
    st.markdown("### 📊 DDP 成本透视 (内部参考)")
    col_t1, col_t2, col_t3, col_t4 = st.columns(4)
    col_t1.metric("1. 基础货值 (含垫资利息)", f"₫ {cif_vnd:,.0f}")
    col_t2.metric("2. 国家税费 (关税+VAT)", f"₫ {(duty_vnd + vat_on_goods_vnd):,.0f}")
    
    # 特别标明本地物流已经包含了“双重”拖车费
    col_t3.metric("3. 越南本地物流总计", f"₫ {total_pod_costs_vnd:,.0f}")
    col_t4.metric("4. 单票占用资金利息", f"₫ {(total_capital_cost_usd * usd_to_vnd):,.0f}")
    
    st.caption(f"🔧 **越南本地物流拆解：** 目的港标准杂费及小费 + 本地仓储费(₫{warehouse_total_vnd:,.0f}) + 港口到仓拖车费 + 仓到客户运费(₫{vn_delivery_to_client_vnd:,.0f})")
