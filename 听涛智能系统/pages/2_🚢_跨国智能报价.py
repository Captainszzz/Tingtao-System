import streamlit as st
import requests
from datetime import datetime

# ==========================================
# 1. 全局配置与移动端自适应 CSS
# ==========================================
st.set_page_config(page_title="听涛智能报价系统", page_icon="🌊", layout="wide")

# 👇 移动端专属优化 CSS 👇
st.markdown("""
<style>
    @media (max-width: 768px) {
        .block-container {
            padding-top: 1.5rem !important;
            padding-left: 0.8rem !important;
            padding-right: 0.8rem !important;
            padding-bottom: 1rem !important;
        }
        h1 { font-size: 1.6rem !important; }
        h2 { font-size: 1.3rem !important; }
        h3 { font-size: 1.1rem !important; }
        .stNumberInput, .stSelectbox { margin-bottom: -0.5rem !important; }
        .stButton>button {
            height: 3.5rem !important;
            font-size: 1.2rem !important;
            font-weight: bold !important;
            border-radius: 8px !important;
        }
        [data-testid="stMetricValue"] { font-size: 1.8rem !important; }
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 数据字典 (多港口自适应矩阵)
# ==========================================
POL_FEES_MATRIX = {
    "厦门/深圳 (按USD一级货代标准)": {
        "currency": "USD",
        "fixed_per_bl": 70 + 30 + 55 + 20 + 25 + 55, 
        "20GP": {"THC": 105, "Booking": 20}, 
        "40GP": {"THC": 165, "Booking": 20}, 
        "40HQ": {"THC": 165, "Booking": 20}  
    },
    "钦州/西南 (按RMB实报实销标准)": {
        "currency": "RMB",
        "fixed_per_bl": 500 + 60 + 50 + 600, 
        "20GP": {"THC": 850, "Heavy_Terminal": 800},   
        "40GP": {"THC": 1250, "Heavy_Terminal": 1000}, 
        "40HQ": {"THC": 1250, "Heavy_Terminal": 1000}  
    }
}

POD_FEES_USD = {
    "fixed_per_do": 48 + 40, 
    "20GP": {"THC": 140, "CIC": 65, "EMS": 25, "Cleaning": 15}, 
    "40GP": {"THC": 222, "CIC": 130, "EMS": 35, "Cleaning": 25}, 
    "40HQ": {"THC": 222, "CIC": 130, "EMS": 35, "Cleaning": 25}  
}

WAREHOUSE_RATES = {
    "storage_per_ton_day": 5200,      
    "handling_pallet": 68000,         
    "handling_loose": 105000          
}

# ==========================================
# 3. 汇率获取引擎
# ==========================================
@st.cache_data(ttl=3600)
def fetch_exchange_rates():
    try:
        data = requests.get("https://api.exchangerate-api.com/v4/latest/CNY", timeout=5).json()
        return {"CNY_USD": data["rates"]["USD"], "CNY_VND": data["rates"]["VND"]}
    except:
        return {"CNY_USD": 0.1388, "CNY_VND": 3460} # 默认防溃

rates = fetch_exchange_rates()

# ==========================================
# 4. 核心主界面
# ==========================================
col_logo, col_title = st.columns([1, 15]) 
with col_logo:
    st.markdown("<h2>🌊</h2>", unsafe_allow_html=True) 
with col_title:
    st.title("听涛智能报价系统")

# 🌟 优化：融合了“财务版”的手动汇率开关，集成在全局设置中
with st.expander("⚙️ 全局设置：汇率风控与利润率 (点击展开)", expanded=False):
    st.markdown("#### 汇率设定 (支持手动锁定)")
    use_manual_fx = st.checkbox("使用手动汇率 (断网或需锁定价格时勾选)", value=False)
    
    if use_manual_fx:
        col_fx1, col_fx2 = st.columns(2)
        with col_fx1:
            manual_usd_cny = st.number_input("市场实时 1 USD = ? RMB", value=7.20)
        with col_fx2:
            manual_usd_vnd = st.number_input("市场实时 1 USD = ? VND", value=24500)
        base_cny_usd = 1 / manual_usd_cny
        base_cny_vnd = manual_usd_vnd / manual_usd_cny
    else:
        base_cny_usd = rates["CNY_USD"]
        base_cny_vnd = rates["CNY_VND"]

    exchange_buffer = st.slider("汇率安全垫 (%)", 0.0, 5.0, 0.8) / 100
    
    # 🛡️ 财务防守逻辑：多收外币以防跌
    effective_usd_rate = base_cny_usd * (1 + exchange_buffer)
    effective_vnd_rate = base_cny_vnd * (1 + exchange_buffer)
    
    real_usd_cny = 1 / base_cny_usd
    effective_usd_cny = 1 / effective_usd_rate
    
    st.info(f"**📉 国际实时中间价:** 1 USD = {real_usd_cny:.4f} RMB\n\n"
            f"**🛡️ 报价结算汇率 (已加安全垫):** 1 USD = {effective_usd_cny:.4f} RMB\n\n"
            f"1 RMB = {effective_vnd_rate:.0f} VND")
    
    st.divider()
    st.markdown("#### 商业利润预留")
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        profit_margin = st.number_input("目标纯利润率 (%)", value=5.0)
    with col_p2:
        loss_rate = st.number_input("破损/隐形成本预留 (%)", value=0.5)

# --- 模块 A: 采购与装载 ---
with st.expander("📦 A. 货物基础参数 (点击展开填写)", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        price_rmb_tax = st.number_input("含税采购价 (RMB/吨)", value=15000, step=500)
    with c2:
        rebate_rate = st.number_input("出口退税率 (%)", value=13)
    with c3:
        packing = st.selectbox("包装方式", ["托盘装 (1吨/托)", "散包 (25kg/包)"])
    with c4:
        tonnage = st.number_input("总重量 (吨)", value=27.0)

    cost_per_ton_rmb = price_rmb_tax - (price_rmb_tax / 1.13 * (rebate_rate/100))
    
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
st.subheader("B. 中国起运段 (China EXW ➔ Ocean Freight)")

st.markdown("🚚 **1. 中国境内拖车**")
domestic_trucking_rmb = st.number_input("工厂/仓库 ➔ 起运港拖车费 (RMB/车)", value=1050.0, step=50.0)
domestic_trucking_usd = domestic_trucking_rmb * effective_usd_rate

st.markdown("🚢 **2. 起运港选择与海运费**")
selected_pol = st.selectbox("⚓ 选择中国起运港口计费模型", list(POL_FEES_MATRIX.keys()))
pol_data = POL_FEES_MATRIX[selected_pol]
currency = pol_data["currency"]

mode = st.radio("运输模式", ["整柜 (FCL)", "散货 (LCL)"], horizontal=True)

total_pol_usd = 0.0
ocean_freight_usd = 0.0

if mode == "整柜 (FCL)":
    l1, l2, l3, l4 = st.columns(4)
    with l1:
        ctype = st.selectbox("选择柜型", ["20GP", "40GP", "40HQ"], index=2)
    with l2:
        ocean_freight_usd = st.number_input("海运费 O/F (USD/柜)", value=300.0, step=50.0)
    with l3:
        has_inspect = st.checkbox("需海关查验", value=False)
    with l4:
        is_telex = st.checkbox("要求电放 (Telex Release)", value=True)
    
    pol_fixed = pol_data["fixed_per_bl"]
    pol_variable = sum(pol_data[ctype].values())
    
    if currency == "RMB":
        telex_fee_rmb = 450 if is_telex else 0
        inspect_fee_rmb = 600 if has_inspect else 0
        total_pol_rmb = pol_fixed + pol_variable + telex_fee_rmb + inspect_fee_rmb
        total_pol_usd = total_pol_rmb * effective_usd_rate
        st.info(f"📍 **{selected_pol} 杂费 (RMB):** ¥{pol_fixed} + ¥{pol_variable} + ¥{telex_fee_rmb} = **¥{total_pol_rmb}** (折合 **${total_pol_usd:.2f}**)")
    else:
        telex_fee_usd = 50 if is_telex else 0
        inspect_fee_usd = 60 if has_inspect else 0
        total_pol_usd = pol_fixed + pol_variable + telex_fee_usd + inspect_fee_usd
        st.info(f"📍 **{selected_pol} 杂费 (USD):** ${pol_fixed} + ${pol_variable} + ${telex_fee_usd} = **${total_pol_usd:.2f}**")

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
st.subheader("C. 越南目的段 (Vietnam POD & Local Services)")

if mode == "整柜 (FCL)":
    pod_fixed = POD_FEES_USD["fixed_per_do"]
    pod_variable = sum(POD_FEES_USD[ctype].values())
    pod_local_fees_usd = pod_fixed + pod_variable
else:
    pod_local_fees_usd = st.number_input("散货目的港杂费 (USD/票)", value=80.0)

pod_fees_vnd_no_tax = pod_local_fees_usd * (effective_vnd_rate / effective_usd_rate)
pod_fees_vat_vnd = pod_fees_vnd_no_tax * 0.08 # 越南本地服务税

d1, d2, d3, d4 = st.columns(4)
with d1:
    import_tax = st.number_input("货物进口关税 (%)", value=0.0)
with d2:
    import_vat = st.number_input("货物进口增值税 (%)", value=0.0)
with d3:
    customs_tip_vnd = st.number_input("海关特殊处理/小费 (VND)", value=0, step=500000)
with d4:
    # 🌟 新增：财务版提及的边境换车费（如适用）
    border_fee_usd = st.number_input("边境/过境换车费 (USD)", value=0.0)

st.markdown("🏢 **海外仓储与末端派送**")
w1, w2, w3 = st.columns(3)
with w1:
    delivery_truck_usd = st.number_input("第一段: 港口 ➔ 仓库拖车 (USD)", value=107.0)
with w2:
    needs_warehousing = st.checkbox("需进入本地仓储转运", value=True)
    storage_days = st.number_input("预计仓储天数", value=7, min_value=0) if needs_warehousing else 0
with w3:
    vn_delivery_to_client_vnd = st.number_input("第二段: 仓库 ➔ 客户本土派送 (VND)", value=0, step=500000)

warehouse_total_vnd = 0
if needs_warehousing:
    storage_fee_vnd = WAREHOUSE_RATES["storage_per_ton_day"] * tonnage * storage_days
    handling_rate = WAREHOUSE_RATES["handling_pallet"] if "托盘" in packing else WAREHOUSE_RATES["handling_loose"]
    handling_fee_vnd = handling_rate * tonnage * 2 
    warehouse_total_vnd = storage_fee_vnd + handling_fee_vnd

st.divider()

# ==========================================
# 5. 终极计算引擎
# ==========================================
if st.button("🚀 一键生成精准报价表", use_container_width=True, type="primary"):
    
    # 1. 货值与 CIF 完税价计算 (税基极其精确)
    total_goods_cost_usd = (cost_per_ton_rmb * tonnage) * effective_usd_rate
    insurance_rate = 0.0008 
    total_cif_usd = (total_goods_cost_usd + domestic_trucking_usd + total_pol_usd + ocean_freight_usd + total_capital_cost_usd) / (1 - (insurance_rate * 1.1))
    
    cif_quote_total_usd = total_cif_usd * (1 + profit_margin/100) * (1 + loss_rate/100)
    cif_quote_per_ton = cif_quote_total_usd / tonnage

    usd_to_vnd = effective_vnd_rate / effective_usd_rate
    cif_vnd = total_cif_usd * usd_to_vnd
    
    # 2. 关税和海关增值税 (严格基于 CIF 计算)
    duty_vnd = cif_vnd * (import_tax / 100)
    vat_on_goods_vnd = (cif_vnd + duty_vnd) * (import_vat / 100)
    
    # 3. 越南本地费用汇总
    local_delivery_port_to_wh_vnd = delivery_truck_usd * usd_to_vnd
    border_fee_vnd = border_fee_usd * usd_to_vnd
    total_pod_costs_vnd = pod_fees_vnd_no_tax + pod_fees_vat_vnd + customs_tip_vnd + warehouse_total_vnd + local_delivery_port_to_wh_vnd + vn_delivery_to_client_vnd + border_fee_vnd
    
    # 4. 最终 DDP 汇总与利润加成
    total_ddp_cost_vnd = cif_vnd + duty_vnd + vat_on_goods_vnd + total_pod_costs_vnd
    ddp_quote_total_vnd = total_ddp_cost_vnd * (1 + profit_margin/100) * (1 + loss_rate/100)
    ddp_quote_per_kg = ddp_quote_total_vnd / (tonnage * 1000)

    st.success("✅ 数据核算完毕！全链路费用已合并，税费计算逻辑严密。")
    
    res1, res2 = st.columns(2)
    with res1:
        st.info("### 方案 A: CIF 胡志明 (USD/吨)")
        st.metric(label="CIF 报价单价", value=f"${cif_quote_per_ton:,.2f}")
        st.markdown(f"**总价:** `${cif_quote_total_usd:,.2f}`")
        
    with res2:
        st.success("### 方案 B: DDP 越南全包 (VND/KG)")
        st.metric(label="DDP 报价单价", value=f"₫ {ddp_quote_per_kg:,.0f}")
        st.markdown(f"**总价:** `₫ {ddp_quote_total_vnd:,.0f}`")
        
    st.markdown("---")
    st.markdown("### 📊 全链路成本透视 (供内部核算对账)")
    col_t1, col_t2, col_t3, col_t4 = st.columns(4)
    
    col_t1.metric("1. 基础货值与垫资利息", f"₫ {cif_vnd:,.0f}")
    col_t2.metric("2. 中国起运段总计", f"${(domestic_trucking_usd + total_pol_usd + ocean_freight_usd):,.2f}")
    col_t3.metric("3. 越南落地与税费总计", f"₫ {(duty_vnd + vat_on_goods_vnd + total_pod_costs_vnd):,.0f}")
    col_t4.metric("4. 本票单次资金利息成本", f"₫ {(total_capital_cost_usd * usd_to_vnd):,.0f}")

    st.caption(f"🔧 **物流链路拆解：** \n"
               f"🇨🇳 **中国段 (¥/${{}})：** 工厂提货 (¥{domestic_trucking_rmb}) ➔ {selected_pol}起运杂费 (${total_pol_usd:.0f}) ➔ 海运费 (${ocean_freight_usd}) \n\n"
               f"🇻🇳 **越南段 (₫)：** 目的港杂费含税 (₫{(pod_fees_vnd_no_tax + pod_fees_vat_vnd):,.0f}) + 换车费/小费 (₫{(border_fee_vnd + customs_tip_vnd):,.0f}) + 仓储装卸 (₫{warehouse_total_vnd:,.0f}) + 港到仓拖车 + 仓到门派送 (₫{vn_delivery_to_client_vnd:,.0f})")

# ==========================================
# 6. 财务风险预警模块 (新增)
# ==========================================
st.markdown("<br>", unsafe_allow_html=True)
with st.expander("⚠️ 财务与操作风险提示 (建议对外报价预留 Buffer)"):
    st.warning("""
    **不可控变动项预警：**
    - **CIC / LSS：** 船公司旺季常调指数，建议向客户标明此项为即期预估价，实报实销。
    - **海关查验：** 若触发查验，除额外查验费外，极易连带产生高额滞箱费/滞港费 (Detention & Demurrage)。
    - **汇率波动：** 尽管系统已预设安全垫，遇极端单边行情仍需锁定汇率或缩短报价单有效期 (建议 3-5 天)。
    """)