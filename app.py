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
                    price REAL NOT NULL)''')
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
    c.execute("PRAGMA table_info(orders)")
    columns = [col[1] for col in c.fetchall()]
    if 'discount' not in columns:
        c.execute("ALTER TABLE orders ADD COLUMN discount REAL DEFAULT 0")
    if 'final_price' not in columns:
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
        # Thay IP máy in Xprinter của quán vào đây (Cổng mạng LAN)
        printer_ip = "192.168.1.100" 
        p = Network(printer_ip, port=9100)
        
        # Tiêu đề Bill
        p.set(align="center", font="a", width=2, height=2)
        p.text("1987 KAFE\n")
        p.set(align="center", font="b")
        p.text("Chuc Quy Khach Mot Ngay Tot Lanh!\n")
        p.text("--------------------------------\n")
        
        # Thông tin bàn
        p.set(align="left")
        p.text(f"Ban/Khach: {table_num}\n")
        p.text(f"Ngay: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
        p.text("--------------------------------\n")
        p.text("Ten Mon          SL    Don Gia    T.Tien\n")
        
        # Danh sách món (Đã ép bỏ dấu Tiếng Việt tránh lỗi font Xprinter)
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
        return True
    except Exception as e:
        st.error(f"Lỗi kết nối máy in: {e}. Vui lòng kiểm tra lại dây mạng của máy Xprinter.")
        return False

# --- GIAO DIỆN CHÍNH ---
st.set_page_config(page_title="Hệ thống Quản lý 1987 Kafe", layout="wide")
st.title("☕ Hệ Thống Quản Lý Quán Cà Phê Bán Hàng (F&B)")

menu_options = ["🛒 Gọi Món & Tính Tiền", "📋 Quản Lý Menu", "📊 Báo Cáo Doanh Thu"]
choice = st.sidebar.selectbox("Chức năng", menu_options)

if choice == "🛒 Gọi Món & Tính Tiền":
    st.header("Thực Đơn Gọi Món")
    menu_data = run_query("SELECT id, name, price FROM menu", fetch=True)
    
    if not menu_data:
        st.warning("Menu trống! Vui lòng qua mục 'Quản Lý Menu' để thêm món.")
    else:
        if 'cart' not in st.session_state:
            st.session_state.cart = {}
            
        col1, col2 = st.columns([5, 4])
        
        with col1:
            st.subheader("Chọn món")
            table_num = st.text_input("Số Bàn / Tên Khách:", "Bàn 01")
            for item in menu_data:
                item_id, name, price = item
                col_name, col_price, col_qty = st.columns([3, 2, 2])
                col_name.write(f"**{name}**")
                col_price.write(f"{price:,.0f} đ")
                qty = col_qty.number_input(f"Số lượng", min_value=0, max_value=20, step=1, key=f"qty_{item_id}")
                if qty > 0:
                    st.session_state.cart[name] = {"price": price, "qty": qty}
                elif name in st.session_state.cart and qty == 0:
                    del st.session_state.cart[name]

        with col2:
            st.subheader("🛒 Hóa Đơn Tạm Tính")
            if not st.session_state.cart:
                st.info("Chưa có món nào được chọn.")
            else:
                total_bill = 0
                invoice_data = []
                for name, info in st.session_state.cart.items():
                    subtotal = info["price"] * info["qty"]
                    total_bill += subtotal
                    invoice_data.append([name, info["qty"], f"{info['price']:,.0f}", f"{subtotal:,.0f}"])
                
                st.table(pd.DataFrame(invoice_data, columns=["Tên Món", "SL", "Đơn Giá", "Thành Tiền"]))
                
                discount_type = st.radio("Loại giảm giá:", ["Theo phần trăm (%)", "Giảm tiền trực tiếp (đ)"], horizontal=True)
                discount_amount = 0
                if discount_type == "Theo phần trăm (%)":
                    discount_value = st.number_input("Nhập % giảm giá:", min_value=0, max_value=100)
                    discount_amount = total_bill * (discount_value / 100)
                else:
                    discount_amount = st.number_input("Nhập số tiền giảm (đ):", min_value=0)

                final_bill = max(0, total_bill - discount_amount)
                st.markdown(f"### **Thành tiền: {final_bill:,.0f} đ**")
                
                if st.button("🔥 Thanh Toán & In Hóa Đơn", type="primary"):
                    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Tiến hành in hóa đơn vật lý
                    print_success = print_xprinter(table_num, st.session_state.cart, total_bill, discount_amount, final_bill)
                    
                    if print_success:
                        # Lưu dữ liệu doanh thu vào database nếu máy in thành công
                        conn = sqlite3.connect('cafe_management.db')
                        c = conn.cursor()
                        c.execute("INSERT INTO orders (table_num, total_price, discount, final_price, created_at) VALUES (?, ?, ?, ?, ?)", 
                                  (table_num, total_bill, discount_amount, final_bill, now))
                        order_id = c.lastrowid
                        for name, info in st.session_state.cart.items():
                            c.execute("INSERT INTO order_details (order_id, item_name, quantity, price) VALUES (?, ?, ?, ?)",
                                      (order_id, name, info["qty"], info["price"]))
                        conn.commit()
                        conn.close()
                        
                        st.success("🎉 Giao dịch thành công, hóa đơn đã được in ra máy Xprinter!")
                        st.session_state.cart = {}
                        st.rerun()

elif choice == "📋 Quản Lý Menu":
    st.header("Quản Lý Danh Mục Món Ăn")
    tab1, tab2 = st.tabs(["➕ Thêm món mới", "👁️ Danh sách & Xóa món"])
    
    with tab1:
        st.subheader("Thêm món vào Menu")
        new_name = st.text_input("Tên đồ uống / món ăn:")
        new_price = st.number_input("Giá bán (VNĐ):", min_value=0, step=1000)
        if st.button("Lưu món"):
            if new_name:
                run_query("INSERT INTO menu (name, price) VALUES (?, ?)", (new_name, new_price))
                st.success(f"Đã thêm thành công: {new_name} - {new_price:,.0f} đ")
                st.rerun()
            else:
                st.error("Vui lòng điền tên món!")
                
    with tab2:
        st.subheader("Danh sách món hiện tại")
        menu_data = run_query("SELECT id, name, price FROM menu", fetch=True)
        if menu_data:
            df_menu = pd.DataFrame(menu_data, columns=["ID", "Tên Món", "Giá (đ)"])
            st.dataframe(df_menu, use_container_width=True)
            
            st.subheader("❌ Xóa món")
            delete_id = st.number_input("Nhập ID món muốn xóa:", min_value=1, step=1)
            if st.button("Xóa ngay"):
                run_query("DELETE FROM menu WHERE id = ?", (delete_id,))
                st.success(f"Đã xóa món có ID {delete_id}")
                st.rerun()
        else:
            st.info("Menu trống.")

elif choice == "📊 Báo Cáo Doanh Thu":
    st.header("Báo Cáo Tình Hình Kinh Doanh")
    orders_data = run_query("SELECT id, table_num, total_price, discount, final_price, created_at FROM orders ORDER BY id DESC", fetch=True)
    
    if not orders_data:
        st.info("Chưa có giao dịch nào được thực hiện.")
    else:
        df_orders = pd.DataFrame(orders_data, columns=["Mã Hóa Đơn", "Bàn/Khách", "Tiền Gốc (đ)", "Giảm Giá (đ)", "Thực Thu (đ)", "Thời Gian"])
        total_revenue = df_orders["Thực Thu (đ)"].sum()
        total_discount = df_orders["Giảm Giá (đ)"].sum()
        total_orders = len(df_orders)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Tổng Doanh Thu (Thực Thu)", f"{total_revenue:,.0f} đ")
        col2.metric("Tổng Tiền Giảm Giá", f"{total_discount:,.0f} đ")
        col3.metric("Tổng Số Hóa Đơn", f"{total_orders} đơn")
        
        st.subheader("Lịch sử hóa đơn chi tiết")
        st.dataframe(df_orders, use_container_width=True)
