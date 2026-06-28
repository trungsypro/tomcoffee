import streamlit as st
import sqlite3
import pandas as pd
import datetime
import random
import string
from escpos.printer import Network, Usb

# --- HÀM TẠO MẬT KHẨU NGẪU NHIÊN ---
def generate_random_password(length=8):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for i in range(length))

# --- CẤU HÌNH CƠ SỞ DỮ LIỆU ---
def init_db():
    conn = sqlite3.connect('cafe_management.db')
    c = conn.cursor()
    # Bảng menu
    c.execute('''CREATE TABLE IF NOT EXISTS menu (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    category TEXT NOT NULL DEFAULT 'Khác')''')
    # Bảng orders
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_num TEXT,
                    total_price REAL,
                    discount REAL DEFAULT 0,
                    final_price REAL,
                    created_at TEXT)''')
    # Bảng chi tiết đơn hàng
    c.execute('''CREATE TABLE IF NOT EXISTS order_details (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER,
                    item_name TEXT,
                    quantity INTEGER,
                    price REAL)''')
    # Bảng quản lý tài khoản (Admin & Nhân viên)
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL)''')
    # Bảng lưu trữ giỏ hàng tạm thời chống mất dữ liệu khi Refresh web
    c.execute('''CREATE TABLE IF NOT EXISTS cart_backup (
                    table_num TEXT,
                    item_name TEXT,
                    quantity INTEGER,
                    price REAL,
                    PRIMARY KEY (table_num, item_name))''')
    # Bảng cấu hình máy in hệ thống (Mới)
    c.execute('''CREATE TABLE IF NOT EXISTS printer_config (
                    id INTEGER PRIMARY KEY,
                    connection_type TEXT DEFAULT 'Network',
                    ip_address TEXT DEFAULT '192.168.1.100',
                    port INTEGER DEFAULT 9100,
                    usb_params TEXT DEFAULT '')''')
    
    # Khởi tạo tài khoản admin mặc định ban đầu nếu chưa có
    c.execute("SELECT COUNT(*) FROM users WHERE role = 'Chủ quán'")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users (username, password, role) VALUES ('tomadmin', 'tom2025', 'Chủ quán')")
        
    # Khởi tạo 3 tài khoản nhân viên ban đầu nếu chưa có
    c.execute("SELECT COUNT(*) FROM users WHERE role = 'Nhân viên'")
    if c.fetchone()[0] == 0:
        for i in range(1, 4):
            user_staff = f"nhanvien{i:02d}"
            pass_staff = generate_random_password()
            c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, 'Nhân viên')", (user_staff, pass_staff))
            
    # Khởi tạo cấu hình máy in mặc định ban đầu nếu chưa có
    c.execute("SELECT COUNT(*) FROM printer_config")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO printer_config (id, connection_type, ip_address, port) VALUES (1, 'Network', '192.168.1.100', 9100)")
            
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

# --- CÁC HÀM XỬ LÝ GIỎ HÀNG TỰ ĐỘNG ĐỒNG BỘ SQLITE ---
def save_cart_item_to_db(table_num, item_name, qty, price):
    if qty > 0:
        run_query("INSERT INTO cart_backup (table_num, item_name, quantity, price) VALUES (?, ?, ?, ?) ON CONFLICT(table_num, item_name) DO UPDATE SET quantity=?", (table_num, item_name, qty, price, qty))
    else:
        run_query("DELETE FROM cart_backup WHERE table_num = ? AND item_name = ?", (table_num, item_name))

def clear_table_cart_from_db(table_num):
    run_query("DELETE FROM cart_backup WHERE table_num = ?", (table_num,))

def load_all_carts_from_db():
    carts = {f"Bàn {i:02d}": {} for i in range(1, 21)}
    data = run_query("SELECT table_num, item_name, quantity, price FROM cart_backup", fetch=True)
    if data:
        for row in data:
            t_num, item, qty, price = row
            if t_num in carts:
                carts[t_num][item] = {"price": price, "qty": qty}
    return carts

# --- HÀM IN HÓA ĐƠN ĐỌC CẤU HÌNH TỪ DATABASE ---
def print_xprinter(table_num, cart_items, total_bill, discount_amount, final_bill):
    try:
        # Lấy cấu hình máy in mới nhất từ cơ sở dữ liệu
        p_config = run_query("SELECT connection_type, ip_address, port FROM printer_config WHERE id = 1", fetch=True)
        if not p_config:
            return False, "Chưa cấu hình máy in"
        
        conn_type, ip_address, port = p_config[0]
        
        if conn_type == "Network (Mạng LAN/Wifi)":
            p = Network(ip_address, port=int(port), timeout=2)
        elif conn_type == "USB (Kết nối trực tiếp)":
            # Mặc định kết nối USB thông dụng (Vendor ID, Product ID tùy dòng máy)
            p = Usb(0x04b8, 0x0202, 0, 0x81, 0x02)
        else:
            return False, "Phương thức kết nối không hỗ trợ"
        
        p.set(align="center", font="a", width=2, height=2)
        p.text("TOM CAFE\n")
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
if 'username' not in st.session_state:
    st.session_state.username = None
if 'show_online_invoice' not in st.session_state:
    st.session_state.show_online_invoice = False
if 'last_invoice_data' not in st.session_state:
    st.session_state.last_invoice_data = {}
    
if 'tables_cart' not in st.session_state:
    st.session_state.tables_cart = load_all_carts_from_db()
if 'selected_table' not in st.session_state:
    st.session_state.selected_table = None

def login(username, password):
    user_data = run_query("SELECT password, role FROM users WHERE username = ?", (username,), fetch=True)
    if user_data and user_data[0][0] == password:
        st.session_state.logged_in = True
        st.session_state.user_role = user_data[0][1] 
        st.session_state.username = username
        st.rerun()
    else:
        st.error("Sai tài khoản hoặc mật khẩu!")

def logout():
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.username = None
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

st.sidebar.markdown(f"**Tài khoản:** {st.session_state.username} ({st.session_state.user_role})")
if st.sidebar.button("Đăng xuất"):
    logout()

if st.session_state.user_role == "Chủ quán":
    menu_options = ["🛒 Gọi Món & Tính Tiền", "📋 Quản Lý Menu", "📊 Báo Cáo Doanh Thu", "⚙️ Cài Đặt Hệ Thống"]
else:
    menu_options = ["🛒 Gọi Món & Tính Tiền"]

choice = st.sidebar.selectbox("Chức năng", menu_options)
LIST_CATEGORIES = ["Cà phê", "Nước ép", "Sinh tố", "Trà trái cây", "Đồ ăn vặt", "Khác"]

# --- CHỨC NĂNG 1: SƠ ĐỒ BÀN & GỌI MÓN ---
if choice == "🛒 Gọi Món & Tính Tiền":
    if st.session_state.show_online_invoice:
        st.warning("⚠️ Đang hiển thị Hóa đơn xem trước (Online Invoice).")
        inv = st.session_state.last_invoice_data
        
        table_rows_html = ""
        for name, info in inv['cart'].items():
            table_rows_html += f"<tr><td>{name}</td><td style='text-align: center;'>{info['qty']}</td><td style='text-align: right;'>{info['price']*info['qty']:,.0f}</td></tr>"
            
        discount_html = ""
        if inv['discount'] > 0:
            discount_html = f"<p style='text-align: right; color: red;'>Giảm giá: -{inv['discount']:,.0f} đ</p>"

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
                    <thead>
                        <tr><th style="text-align: left;">Món</th><th style="text-align: center;">SL</th><th style="text-align: right;">T.Tien</th></tr>
                    </thead>
                    <tbody>
                        {table_rows_html}
                    </tbody>
                </table>
                <hr style="border-top: 1px dashed #333;">
                <p style="text-align: right;">Tổng tiền gốc: {inv['total']:,.0f} đ</p>
                {discount_html}
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
            
    else:
        st.header("🗺️ Sơ Đồ Bàn Ghế & Gọi Món")
        st.subheader("Trạng thái phòng bàn hiện tại:")
        table_cols = st.columns(5)
        
        st.session_state.tables_cart = load_all_carts_from_db()
        
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
                                
                                if qty != current_qty:
                                    if qty > 0:
                                        st.session_state.tables_cart[active_table][name] = {"price": price, "qty": qty}
                                    elif name in st.session_state.tables_cart[active_table] and qty == 0:
                                        del st.session_state.tables_cart[active_table][name]
                                    save_cart_item_to_db(active_table, name, qty, price)
                                    st.rerun()

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
                        
                        btn_c1, btn_c2 = st.columns(2)
                        with btn_c1:
                            pay_clicked = st.button("🔥 Thanh Toán & In Bill", type="primary", use_container_width=True, key=f"pay_btn_{active_table}")
                        with btn_c2:
                            clear_clicked = st.button("🗑️ Xóa Đơn Tạm Thời", type="secondary", use_container_width=True, key=f"clear_btn_{active_table}")
                        
                        if pay_clicked:
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
                            
                            clear_table_cart_from_db(active_table) 
                            st.session_state.tables_cart[active_table] = {} 
                            st.session_state.selected_table = None 
                            
                            if print_success:
                                st.success("🎉 Đã in hoá đơn thành công ra máy Xprinter!")
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
                                st.session_state.show_online_invoice = True
                                st.rerun()
                        
                        if clear_clicked:
                            clear_table_cart_from_db(active_table)
                            st.session_state.tables_cart[active_table] = {}
                            st.session_state.selected_table = None
                            st.success(f"🧹 Đã hủy toàn bộ món tạm tính của {active_table}!")
                            st.rerun()
        else:
            st.info("💡 Vui lòng bấm chọn một bàn phía trên để tiến hành lên đơn gọi món.")

# --- CHỨC NĂNG 2: QUẢN LÝ MENU ---
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

# --- CHỨC NĂNG 3: BÁO CÁO DOANH THU ---
elif choice == "📊 Báo Cáo Doanh Thu" and st.session_state.user_role == "Chủ quán":
    st.header("📊 Báo Cáo Doanh Thu & Tình Hình Kinh Doanh")
    st.markdown("### 🔍 Chọn Bộ Lọc Thời Gian")
    time_filter = st.radio(
        "Xem doanh thu theo:", 
        ["Hôm nay", "Hôm qua", "Tuần này", "Tháng này", "Khoảng thời gian tùy chọn"], 
        horizontal=True
    )
    
    today = datetime.date.today()
    start_date = today
    end_date = today

    if time_filter == "Hôm nay":
        start_date = today
        end_date = today
    elif time_filter == "Hôm qua":
        start_date = today - datetime.timedelta(days=1)
        end_date = today - datetime.timedelta(days=1)
    elif time_filter == "Tuần này":
        start_date = today - datetime.timedelta(days=today.weekday())
        end_date = today
    elif time_filter == "Tháng này":
        start_date = today.replace(day=1)
        end_date = today
    elif time_filter == "Khoảng thời gian tùy chọn":
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            start_date = st.date_input("Từ ngày:", today - datetime.timedelta(days=7))
        with col_d2:
            end_date = st.date_input("Đến ngày:", today)
            
    start_str = f"{start_date} 00:00:00"
    end_str = f"{end_date} 23:59:59"
    
    query_report = "SELECT id, table_num, total_price, discount, final_price, created_at FROM orders WHERE created_at BETWEEN ? AND ? ORDER BY id DESC"
    orders_data = run_query(query_report, (start_str, end_str), fetch=True)
    
    st.markdown("---")
    st.subheader(f"📋 Kết quả báo cáo từ ngày {start_date.strftime('%d/%m/%Y')} đến {end_date.strftime('%d/%m/%Y')}:")
    
    if not orders_data:
        st.info("Không tìm thấy giao dịch nào phát sinh trong khoảng thời gian đã chọn.")
    else:
        df_orders = pd.DataFrame(orders_data, columns=["Mã Hóa Đơn", "Bàn/Khách", "Tiền Gốc (đ)", "Giảm Giá (đ)", "Thực Thu (đ)", "Thời Gian"])
        m1, m2, m3 = st.columns(3)
        m1.metric("💰 Tổng Thực Thu", f"{df_orders['Thực Thu (đ)'].sum():,.0f} đ")
        m2.metric("📉 Tổng Giảm Giá", f"{df_orders['Giảm Giá (đ)'].sum():,.0f} đ")
        m3.metric("🧾 Số Lượng Đơn", f"{len(df_orders)} hóa đơn")
        st.dataframe(df_orders, use_container_width=True)
        
        st.markdown("---")
        st.markdown("🛠️ **Quản lý hóa đơn lỗi:**")
        del_order_id = st.number_input("Nhập mã hóa đơn muốn xóa lỗi khỏi hệ thống:", min_value=1, step=1)
        if st.button("Xóa hóa đơn"):
            run_query("DELETE FROM orders WHERE id = ?", (del_order_id,))
            st.success(f"Đã xóa hóa đơn mã số {del_order_id} thành công.")
            st.rerun()

# --- CHỨC NĂNG 4: CÀI ĐẶT HỆ THỐNG (ĐÃ TÍCH HỢP TAB CẤU HÌNH MÁY IN) ---
elif choice == "⚙️ Cài Đặt Hệ Thống" and st.session_state.user_role == "Chủ quán":
    st.header("⚙️ Cài Đặt Hệ Thống & Cấu Hình")
    
    tab_admin, tab_printer, tab_list, tab_add, tab_edit = st.tabs([
        "👑 Tài khoản Admin", 
        "🖨️ Cấu hình Máy in",
        "👥 Danh sách nhân viên", 
        "➕ Thêm nhân viên mới", 
        "✏️ Sửa mật khẩu / Xóa nhân viên"
    ])
    
    with tab_admin:
        st.subheader("Thay đổi tài khoản quản trị (Chủ quán)")
        current_admin = st.session_state.username
        admin_db_pass = run_query("SELECT password FROM users WHERE username = ?", (current_admin,), fetch=True)[0][0]
        new_admin_user = st.text_input("Tên đăng nhập Admin mới:", value=current_admin)
        new_admin_pass = st.text_input("Mật khẩu Admin mới:", value=admin_db_pass, type="password")
        
        if st.button("Cập nhật tài khoản Admin", type="primary"):
            if not new_admin_user or not new_admin_pass:
                st.error("Không được để trống tên đăng nhập hoặc mật khẩu!")
            else:
                conn = sqlite3.connect('cafe_management.db')
                c = conn.cursor()
                c.execute("DELETE FROM users WHERE username = ?", (current_admin,))
                try:
                    c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, 'Chủ quán')", (new_admin_user, new_admin_pass))
                    conn.commit()
                    st.success("🎉 Đã cập nhật tài khoản Admin thành công! Hệ thống tự động đăng xuất để bạn đăng nhập lại.")
                    conn.close()
                    logout()
                except sqlite3.IntegrityError:
                    st.error("Tên đăng nhập này đã bị trùng với một tài khoản khác trong hệ thống!")
                    conn.close()
                    
    # --- TAB CẤU HÌNH MÁY IN MỚI THÊM THEO YÊU CẦU ---
    with tab_printer:
        st.subheader("🛠️ Thiết lập thông số Máy in Hóa đơn Xprinter")
        
        # Đọc cấu hình hiện tại từ DB
        current_p = run_query("SELECT connection_type, ip_address, port FROM printer_config WHERE id = 1", fetch=True)[0]
        
        p_type = st.selectbox(
            "Phương thức kết nối máy in:", 
            ["Network (Mạng LAN/Wifi)", "USB (Kết nối trực tiếp vào máy chủ)"],
            index=0 if current_p[0] == "Network" or "Network" in current_p[0] else 1
        )
        
        if p_type == "Network (Mạng LAN/Wifi)":
            st.info("💡 Đảm bảo máy in và cục Wifi của quán chung một lớp mạng (Ví dụ: Máy in IP là 192.168.1.100 thì điện thoại/máy tính cũng bắt Wifi lớp 192.168.1.x)")
            new_ip = st.text_input("Địa chỉ IP Máy in hiện tại:", value=current_p[1])
            new_port = st.number_input("Cổng kết nối (Port - Mặc định là 9100):", value=int(current_p[2]), min_value=1)
        else:
            st.warning("⚠️ Chế độ USB chỉ hoạt động khi bạn cài đặt app chạy local ngay tại máy tính ở quầy và cắm dây USB máy in trực tiếp.")
            new_ip = current_p[1]
            new_port = current_p[2]
            
        if st.button("💾 Lưu cấu hình máy in", type="primary"):
            run_query("UPDATE printer_config SET connection_type = ?, ip_address = ?, port = ? WHERE id = 1", 
                      (p_type, new_ip, new_port))
            st.success("🎉 Đã cập nhật thông số cấu hình máy in thành công! Hệ thống sẽ áp dụng ngay cho lượt in tiếp theo.")
            st.rerun()
                    
    with tab_list:
        st.subheader("Danh sách nhân viên hiện tại")
        users_data = run_query("SELECT username, password FROM users WHERE role = 'Nhân viên'", fetch=True)
        if users_data:
            df_users = pd.DataFrame(users_data, columns=["Tên đăng nhập", "Mật khẩu hiện tại"])
            st.dataframe(df_users, use_container_width=True)
        else:
            st.info("Chưa có nhân viên nào trong hệ thống.")
            
    with tab_add:
        st.subheader("Tạo tài khoản nhân viên mới")
        add_username = st.text_input("Tên đăng nhập mới (Ví dụ: nhanvien04):")
        col_p1, col_p2 = st.columns([3, 1])
        with col_p1:
            add_password = st.text_input("Mật khẩu (Để trống nếu muốn tạo ngẫu nhiên):", type="password")
        with col_p2:
            st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
            generate_click = st.button("Tạo ngẫu nhiên")
            
        if generate_click:
            st.session_state.temp_generated_pass = generate_random_password()
            st.info(f"Mật khẩu ngẫu nhiên vừa sinh ra: **{st.session_state.temp_generated_pass}**")
            
        if st.button("Thêm nhân viên"):
            if not add_username:
                st.error("Vui lòng nhập Tên đăng nhập!")
            else:
                check_exist = run_query("SELECT username FROM users WHERE username = ?", (add_username,), fetch=True)
                if check_exist:
                    st.error("Tên đăng nhập này đã tồn tại trên hệ thống!")
                else:
                    final_pass = add_password if add_password else st.session_state.get('temp_generated_pass', '12345678')
                    run_query("INSERT INTO users (username, password, role) VALUES (?, ?, 'Nhân viên')", (add_username, final_pass))
                    st.success(f"Đã thêm thành công tài khoản: **{add_username}**")
                    if 'temp_generated_pass' in st.session_state:
                        del st.session_state.temp_generated_pass
                    st.rerun()
                    
    with tab_edit:
        st.subheader("Cập nhật mật khẩu hoặc Xóa nhân viên")
        all_staff = [u[0] for u in run_query("SELECT username FROM users WHERE role = 'Nhân viên'", fetch=True)]
        
        if not all_staff:
            st.info("Không có nhân viên để thao tác.")
        else:
            selected_staff = st.selectbox("Chọn nhân viên cần xử lý:", all_staff)
            new_staff_pass = st.text_input("Nhập mật khẩu mới muốn đổi:", type="password")
            if st.button("Cập nhật mật khẩu nhân viên"):
                if new_staff_pass:
                    run_query("UPDATE users SET password = ? WHERE username = ?", (new_staff_pass, selected_staff))
                    st.success(f"Đã đổi mật khẩu thành công cho nhân viên **{selected_staff}**!")
                    st.rerun()
                else:
                    st.error("Vui lòng điền mật khẩu mới!")
            
            st.markdown("---")
            st.markdown(f"⚠️ **Khu vực nguy hiểm:**")
            if st.button(f"❌ Xóa hoàn toàn nhân viên {selected_staff}", type="secondary"):
                run_query("DELETE FROM users WHERE username = ?", (selected_staff,))
                st.success(f"Đã xóa tài khoản **{selected_staff}** khỏi hệ thống.")
                st.rerun()
