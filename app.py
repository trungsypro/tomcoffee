import streamlit as st
import sqlite3
import pandas as pd
import datetime
from escpos.printer import Network, Usb

# --- CẤU HÌNH CƠ SỞ DỮ LIỆU ---
def init_db():
    conn = sqlite3.connect('cafe_management.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS menu (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    category TEXT NOT NULL DEFAULT 'Khác')''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_num TEXT,
                    total_price REAL,
                    discount REAL DEFAULT 0,
                    final_price REAL,
                    created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS order_details (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER,
                    item_name TEXT,
                    quantity INTEGER,
                    price REAL)''')
    conn.commit()
    conn.close()

init_db()

def upgrade_db_structure():
    conn = sqlite3.connect('cafe_management.db')
    c = conn.cursor()
    c.execute("PRAGMA table_info(menu)")
    columns = [col[1] for col in c.fetchall()]
    if 'category' not in columns:
        c.execute("ALTER TABLE menu ADD COLUMN category TEXT NOT NULL DEFAULT 'Khác'")
        
    c.execute("PRAGMA table_info(orders)")
    columns_orders = [col[1] for col in c.fetchall()]
    if 'discount' not in columns_orders:
        c.execute("ALTER TABLE orders ADD COLUMN discount REAL DEFAULT 0")
    if 'final_price' not in columns_orders:
        c.execute("ALTER TABLE orders ADD COLUMN final_price REAL")
    conn.commit()
    conn.close()

upgrade_db_structure()

def run_query(query, params=(), fetch=False):
    conn = sqlite3.connect('cafe_management.db')
    c = conn.cursor()
    c.execute(query, params)
    data = None
    if fetch:
        data = c.fetchall()
    conn.commit()
    conn.close()
    return data

# --- HÀM IN HÓA ĐƠN QUA XPRINTER ---
def print_xprinter(table_num, cart_items, total_bill, discount_amount, final_bill):
    try:
        printer_ip = "192.168.1.100" 
        # Giới hạn timeout 2 giây để tránh bị treo đơ giao diện khi mất kết nối máy in
        p = Network(printer_ip, port=9100, timeout=2)
        
        p.set(align="center", font="a", width=2, height=2)
        p.text("TOM CAFE\n") # Máy in nhiệt in chữ không dấu để tránh lỗi font kí tự đặc biệt
        p.set(align="center", font="b")
        p.text("Chuc Quy Khach Mot Ngay Tot Lanh!\n")
        p.text("--------------------------------\n")
        
        p.set(align="left")
        p.text(f"Ban/Khach: {table_num}\n")
        p.text(f"Ngay: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
        p.text("--------------------------------\n")
        p.text("Ten Mon          SL    Don Gia    T.Tien\n")
        
        for name, info in cart_items.items():
            subtotal = info["price"] * info["qty"]
            name_unsigned = name.encode('ascii', 'ignore').decode('ascii')
            line = f"{name_unsigned:<16} {info['qty']:<5} {info['price']:,.0f} \n"
            p.text(line)
            
        p.text("--------------------------------\n")
        p.text(f"Tong tien goc: {total_bill:,.0f} d\n")
        if discount_amount > 0:
            p.text(f"Giam gia: -{discount_amount:,.0f} d\n")
        
        p.set(align="right", font="a", width=1, height=1)
        p.text(f"THANH TIEN: {final_bill:,.0f} d\n\n")
        
        p.set(align="center", font="b")
        p.text("Cam on Quy Khach! Hen gap lai!\n")
        p.cut()
        return True, "Success"
    except Exception as e:
        return False, str(e)

# --- HỆ THỐNG ĐĂNG NHẬP & TRẠNG THÁI ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_role' not in st.session_state:
    st.session_state.user_role = None
if 'show_online_invoice' not in st.session_state:
    st.session_state.show_online_invoice = False
if 'last_invoice_data' not in st.session_state:
    st.session_state.last_invoice_data = {}
    
if 'tables_cart' not in st.session_state:
    st.session_state.tables_cart = {f"Bàn {i:02d}": {} for i in range(1, 21)}
if 'selected_table' not in st.session_state:
    st.session_state.selected_table = None

def login(username, password):
    if username == "chuquan" and password == "1987admin":
        st.session_state.logged_in = True
        st.session_state.user_role = "Chủ quán"
        st.rerun()
    elif username == "nhanvien" and password == "1987nhanvien":
        st.session_state.logged_in = True
        st.session_state.user_role = "Nhân viên"
        st.rerun()
    else:
        st.error("Sai tài khoản hoặc mật khẩu!")

def logout():
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.show_online_invoice = False
    st.rerun()

# --- GIAO DIỆN HỆ THỐNG TOM CAFÉ ---
st.set_page_config(page_title="Hệ thống Quản lý TOM CAFÉ", layout="wide")

if not st.session_state.logged_in:
    st.title("🔑 ĐĂNG NHẬP HỆ THỐNG F&B")
    col_login, _ = st.columns([1, 1])
    with col_login:
        user_input = st.text_input("Tài khoản:")
        pass_input = st.text_input("Mật khẩu:", type="password")
        if st.button("Đăng nhập", type="primary"):
            login(user_input, pass_input)
    st.stop()

st.sidebar.markdown(f"**Tài khoản:** {st.session_state.user_role}")
if st.sidebar.button("Đăng xuất"):
    logout()

if st.session_state.user_role == "Chủ quán":
    menu_options = ["🛒 Gọi Món & Tính Tiền", "📋 Quản Lý Menu", "📊 Báo Cáo Doanh Thu"]
else:
    menu_options = ["🛒 Gọi Món & Tính Tiền"]

choice = st.sidebar.selectbox("Chức năng", menu_options)
LIST_CATEGORIES = ["Cà phê", "Nước ép", "Sinh tố", "Trà trái cây", "Đồ ăn vặt", "Khác"]

# --- CHỨC NĂNG 1: SƠ ĐỒ BÀN & GỌI MÓN ---
if choice == "🛒 Gọi Món & Tính Tiền":
    
    # TRƯỜNG HỢP 1: HIỂN THỊ HÓA ĐƠN ONLINE (KHI KHÔNG CÓ MÁY IN)
    if st.session_state.show_online_invoice:
        st.warning("⚠️ Không tìm thấy máy in Xprinter! Đang hiển thị Hóa đơn Online.")
        inv = st.session_state.last_invoice_data
        st.markdown(
            f"""
            <div style="background-color: #f8f9fa; padding: 25px; border-radius: 10px; border: 1px dashed #333; max-width: 400px; margin: auto; font-family: 'Courier New', Courier, monospace; color: black;">
                <h2 style="text-align: center; margin-bottom: 5px;">TOM CAFÉ</h2>
                <p style="text-align: center; font-size: 12px; margin-top: 0;">HÓA ĐƠN THANH TOÁN</p>
                <hr style="border-top: 1px dashed #333;">
                <p><b>Vị trí:</b> {inv['table_num']}</p>
                <p><b>Thời gian:</b> {inv['date']}</p>
                <hr style="border-top: 1px dashed #333;">
                <table style="width: 100%; font-size: 14px;">
                    <tr><th style="text-align: left;">Món</th><th style="text-align: center;">SL</th><th style="text-align: right;">T.Tien</th></tr>
                    {"".join([f"<tr><td>{name}</td><td style='text-align: center;'>{info['qty']}</td><td style='text-align: right;'>{info['price']*info['qty']:,.0f}</td></tr>" for name, info in inv['cart'].items()])}
                </table>
                <hr style="border-top: 1px dashed #333;">
                <p style="text-align: right;">Tổng tiền gốc: {inv['total']:,.0f} đ</p>
                {"<p style='text-align: right; color: red;'>Giảm giá: -{:,.0f} đ</p>".format(inv['discount']) if inv['discount'] > 0 else ""}
                <h3 style="text-align: right; margin-top: 10px;">THÀNH TIỀN: {inv['final']:,.0f} đ</h3>
                <hr style="border-top: 1px dashed #333;">
                <p style="text-align: center; font-size: 12px;">Cảm ơn Quý Khách - Hẹn gặp lại!</p>
            </div>
            """, unsafe_allow_html=True
        )
        if st.button("🔄 Quay lại Sơ đồ bàn", type="primary"):
            st.session_state.show_online_invoice = False
            st.session_state.last_invoice_data = {}
            st.rerun()
            
    # TRƯỜNG HỢP 2: HIỂN THỊ SƠ ĐỒ PHÒNG BÀN
    else:
        st.header("🗺️ Sơ Đồ Bàn Ghế & Gọi Món")
        st.subheader("Trạng thái phòng bàn hiện tại:")
        table_cols = st.columns(5)
        
        for i in range(1, 21):
            t_name = f"Bàn {i:02d}"
            col_idx = (i - 1) % 5
            has_items = len(st.session_state.tables_cart[t_name]) > 0
            
            with table_cols[col_idx]:
                btn_label = f"🟢 {t_name} (Trống)" if not has_items else f"🔴 {t_name} (Có khách)"
                is_selected = (st.session_state.selected_table == t_name)
                btn_type = "primary" if is_selected else "secondary"
                
                if st.button(btn_label, key=f"btn_{t_name}", use_container_width=True, type=btn_type):
                    st.session_state.selected_table = t_name
                    st.rerun()
        
        st.markdown("---")
        
        if st.session_state.selected_table:
            active_table = st.session_state.selected_table
            st.subheader(f"📋 Đang xử lý đơn cho: {active_table}")
            
            menu_data = run_query("SELECT id, name, price, category FROM menu", fetch=True)
            if not menu_data:
                st.warning("Menu trống! Vui lòng liên hệ Chủ quán để thêm món.")
            else:
                col1, col2 = st.columns([5, 4])
                
                with col1:
                    st.markdown("**Menu đồ uống & đồ ăn vặt:**")
                    df_current_menu = pd.DataFrame(menu_data, columns=["id", "name", "price", "category"])
                    available_categories = df_current_menu["category"].unique()
                    tabs = st.tabs(list(available_categories))
                    
                    for index, cat_name in enumerate(available_categories):
                        with tabs[index]:
                            df_filtered = df_current_menu[df_current_menu["category"] == cat_name]
                            for _, row in df_filtered.iterrows():
                                item_id, name, price = row["id"], row["name"], row["price"]
                                col_name, col_price, col_qty = st.columns([3, 2, 2])
                                col_name.write(f"**{name}**")
                                col_price.write(f"{price:,.0f} đ")
                                
                                current_qty = st.session_state.tables_cart[active_table].get(name, {}).get("qty", 0)
                                qty = col_qty.number_input(f"SL", min_value=0, max_value=20, step=1, value=current_qty, key=f"qty_{active_table}_{item_id}")
                                
                                if qty > 0:
                                    st.session_state.tables_cart[active_table][name] = {"price": price, "qty": qty}
                                elif name in st.session_state.tables_cart[active_table] and qty == 0:
                                    del st.session_state.tables_cart[active_table][name]

                with col2:
                    st.markdown(f"**🛒 Chi tiết hóa đơn tạm tính của {active_table}:**")
                    current_cart = st.session_state.tables_cart[active_table]
                    
                    if not current_cart:
                        st.info("Bàn này chưa chọn món.")
                    else:
                        total_bill = 0
                        invoice_data = []
                        for name, info in current_cart.items():
                            subtotal = info["price"] * info["qty"]
                            total_bill += subtotal
                            invoice_data.append([name, info["qty"], f"{info['price']:,.0f}", f"{subtotal:,.0f}"])
                        
                        st.table(pd.DataFrame(invoice_data, columns=["Tên Món", "SL", "Đơn Giá", "Thành Tiền"]))
                        
                        discount_type = st.radio("Loại giảm giá:", ["Theo phần trăm (%)", "Giảm tiền trực tiếp (đ)"], horizontal=True, key=f"disc_type_{active_table}")
                        discount_amount = 0
                        if discount_type == "Theo phần trăm (%)":
                            discount_value = st.number_input("Nhập % giảm giá:", min_value=0, max_value=100, key=f"disc_val_p_{active_table}")
                            discount_amount = total_bill * (discount_value / 100)
                        else:
                            discount_amount = st.number_input("Nhập số tiền giảm (đ):", min_value=0, key=f"disc_val_d_{active_table}")

                        final_bill = max(0, total_bill - discount_amount)
                        st.markdown(f"### **Thành tiền: {final_bill:,.0f} đ**")
                        
                        if st.button("🔥 Thanh Toán & In Hóa Đơn", type="primary", key=f"pay_btn_{active_table}"):
                            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
                            print_success, error_msg = print_xprinter(active_table, current_cart, total_bill, discount_amount, final_bill)
                            
                            conn = sqlite3.connect('cafe_management.db')
                            c = conn.cursor()
                            c.execute("INSERT INTO orders (table_num, total_price, discount, final_price, created_at) VALUES (?, ?, ?, ?, ?)", 
                                      (active_table, total_bill, discount_amount, final_bill, now))
                            order_id = c.lastrowid
                            for name, info in current_cart.items():
                                c.execute("INSERT INTO order_details (order_id, item_name, quantity, price) VALUES (?, ?, ?, ?)",
                                          (order_id, name, info["qty"], info["price"]))
                            conn.commit()
                            conn.close()
                            
                            if print_success:
                                st.success("🎉 Đã in hoá đơn thành công ra máy Xprinter!")
                                st.session_state.tables_cart[active_table] = {} 
                                st.session_state.selected_table = None
                                st.rerun()
                            else:
                                st.session_state.last_invoice_data = {
                                    "table_num": active_table,
                                    "date": now,
                                    "cart": current_cart.copy(),
                                    "total": total_bill,
                                    "discount": discount_amount,
                                    "final": final_bill
                                }
                                st.session_state.tables_cart[active_table] = {} 
                                st.session_state.selected_table = None
                                st.session_state.show_online_invoice = True
                                st.rerun()
        else:
            st.info("💡 Vui lòng bấm chọn một bàn phía trên để tiến hành lên đơn gọi món.")

# --- CHỨC NĂNG 2 VÀ 3 ---
elif choice == "📋 Quản Lý Menu" and st.session_state.user_role == "Chủ quán":
    st.header("Quản Lý Danh Mục Món Ăn")
    tab1, tab2 = st.tabs(["➕ Thêm món mới", "👁️ Danh sách & Xóa món"])
    with tab1:
        st.subheader("Thêm món vào Menu")
        new_name = st.text_input("Tên đồ uống / món ăn:")
        new_price = st.number_input("Giá bán (VNĐ):", min_value=0, step=1000)
        new_category = st.selectbox("Chọn nhóm danh mục chính:", LIST_CATEGORIES)
        if st.button("Lưu món"):
            if new_name:
                run_query("INSERT INTO menu (name, price, category) VALUES (?, ?, ?)", (new_name, new_price, new_category))
                st.success(f"Đã thêm thành công: [{new_category}] {new_name}")
                st.rerun()
    with tab2:
        menu_data = run_query("SELECT id, name, price, category FROM menu ORDER BY category ASC", fetch=True)
        if menu_data:
            st.dataframe(pd.DataFrame(menu_data, columns=["ID", "Tên Món", "Giá (đ)", "Danh Mục"]), use_container_width=True)
            delete_id = st.number_input("Nhập ID món muốn xóa:", min_value=1, step=1)
            if st.button("Xóa ngay"):
                run_query("DELETE FROM menu WHERE id = ?", (delete_id,))
                st.rerun()

elif choice == "📊 Báo Cáo Doanh Thu" and st.session_state.user_role == "Chủ quán":
    st.header("Báo Cáo Tình Hình Kinh Doanh")
    orders_data = run_query("SELECT id, table_num, total_price, discount, final_price, created_at FROM orders ORDER BY id DESC", fetch=True)
    if not orders_data:
        st.info("Chưa có giao dịch nào.")
    else:
        df_orders = pd.DataFrame(orders_data, columns=["Mã Hóa Đơn", "Bàn/Khách", "Tiền Gốc (đ)", "Giảm Giá (đ)", "Thực Thu (đ)", "Thời Gian"])
        st.columns(3)[0].metric("Tổng Doanh Thu", f"{df_orders['Thực Thu (đ)'].sum():,.0f} đ")
        st.columns(3)[1].metric("Tổng Giảm Giá", f"{df_orders['Giảm Giá (đ)'].sum():,.0f} đ")
        st.columns(3)[2].metric("Tổng Hóa Đơn", f"{len(df_orders)} đơn")
        st.dataframe(df_orders, use_container_width=True)
        del_order_id = st.number_input("Nhập mã hóa đơn muốn xóa lỗi:", min_value=1, step=1)
        if st.button("Xóa hóa đơn"):
            run_query("DELETE FROM orders WHERE id = ?", (del_order_id,))
            st.rerun()
