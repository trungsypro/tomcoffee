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
    # Bảng lưu trữ giỏ hàng tạm thời chống mất dữ liệu khi Refresh web (Mới)
    c.execute('''CREATE TABLE IF NOT EXISTS cart_backup (
                    table_num TEXT,
                    item_name TEXT,
                    quantity INTEGER,
                    price REAL,
                    PRIMARY KEY (table_num, item_name))''')
    
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

# --- HÀM IN HÓA ĐƠN QUA XPRINTER ---
def print_xprinter(table_num, cart_items, total_bill, discount_amount, final_bill):
    try:
        printer_ip = "192.168.1.100" 
        p = Network(printer_ip, port=9100, timeout=2)
        
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
    
# Tải toàn bộ dữ liệu giỏ hàng từ Cơ sở dữ liệu lên thay vì để trống
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
        st.warning("⚠️ Không tìm thấy máy in Xprinter! Đang hiển thị Hóa đơn Online.")
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
        
        # Đọc dữ liệu mới nhất từ DB để vẽ màu sơ đồ bàn chính xác nhất
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
                                
                                # Nếu thay đổi số lượng, tự động cập nhật cả vào bộ nhớ tạm và DB SQL
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
                        
                        # Thiết lập 2 nút hành động: Thanh toán và Hủy/Xóa đơn tạm
                        btn_c1, btn_c2 = st.columns(2)
                        with btn_c1:
                            pay_clicked = st.button("🔥 Thanh Toán & In Bill", type="primary", use_container_width=True, key=f"pay_btn_{active_table}")
                        with btn_c2:
                            clear_clicked = st.button("🗑️ Xóa Đơn Tạm Thời", type="secondary", use_container_width=True, key=f"clear_btn_{active_table}")
                        
                        # HÀNH ĐỘNG 1: BẤM THANH TOÁN
                        if pay_clicked:
                            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            print_success, error_msg = print_xprinter(active_table, current_cart, total_bill, discount_amount, final_bill)
                            
                            # Lưu hóa đơn chính thức vào lịch sử doanh thu
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
                            
                            # GIẢI PHÓNG PHÒNG BÀN (LÀM TRỐNG BÀN SAU THANH TOÁN)
                            clear_table_cart_from_db(active_table) # Xóa sạch giỏ tạm trong CSDL
                            st.session_state.tables_cart[active_table] = {} # Xóa sạch giỏ trong RAM
                            st.session_state.selected_table = None # Bỏ chọn bàn
                            
                            if print_success:
                                st.success("🎉 Đã in hoá đơn thành công ra máy Xprinter! Bàn đã được đưa về trạng thái trống.")
                                st.rerun()
                            else:
                                # Nếu lỗi máy in, chuyển dữ liệu sang hóa đơn online nhưng bàn vẫn được giải phóng trống
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
                        
                        # HÀNH ĐỘNG 2: BẤM XÓA ĐƠN TẠM (Để reset bàn về Trống khi không dùng nữa)
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

# --- CHỨC NĂNG 4: CÀI ĐẶT TÀI KHOẢN HỆ THỐNG ---
elif choice == "⚙️ Cài Đặt Hệ Thống" and st.session_state.user_role == "Chủ quán":
    st.header("⚙️ Cài Đặt Hệ Thống & Quản Lý Tài Khoản")
    
    tab_admin, tab_list, tab_add, tab_edit = st.tabs([
        "👑 Tài khoản Admin", 
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
            st.info(f"Mật khẩu ngẫu nhiên vừa sinh ra: **{st.session_state.temp_generated_pass}** (Vui lòng copy lại)")
            
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
