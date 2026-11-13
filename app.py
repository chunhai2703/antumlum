import os, secrets, io, base64
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import inspect, text

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'CHANGE_ME_BEFORE_DEPLOYMENT')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///antumlum.db').replace('postgres://', 'postgresql://', 1)
db = SQLAlchemy(app)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=False)

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), unique=True, nullable=False)
    email = db.Column(db.String(120))
    password_hash = db.Column(db.String(255))
    member_token = db.Column(db.String(64), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(24))
    points = db.Column(db.Integer, default=0, nullable=False)
    total_spent = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Integer, default=0)
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship('Customer', backref='transactions')

class Voucher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), default='')
    points_cost = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, default=0, nullable=False)
    active = db.Column(db.Boolean, default=True)

class Redemption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    voucher_id = db.Column(db.Integer, db.ForeignKey('voucher.id'), nullable=False)
    code = db.Column(db.String(32), unique=True, nullable=False)
    status = db.Column(db.String(20), default='issued')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship('Customer')
    voucher = db.relationship('Voucher')

class SaleOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_code = db.Column(db.String(32), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    payment_method = db.Column(db.String(30), nullable=False, default='MoMo/VietQR')
    payment_note = db.Column(db.String(120))
    status = db.Column(db.String(20), nullable=False, default='pending')
    points_awarded = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime)
    customer = db.relationship('Customer')


def setting(key, default):
    row = Setting.query.filter_by(key=key).first()
    return row.value if row else default

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('admin_id'):
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapped

def member_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('customer_id'):
            return redirect(url_for('member_login', next=request.path))
        return fn(*args, **kwargs)
    return wrapped

@app.context_processor
def globals_for_templates():
    return {'brand_name': 'AnTumLum', 'point_rate': setting('point_rate', '10000'), 'now_year': datetime.now().year}

@app.route('/')
def home():
    if session.get('admin_id'): return redirect(url_for('dashboard'))
    if session.get('customer_id'): return redirect(url_for('member_home'))
    return redirect(url_for('member_login'))

# ---------------- ADMIN / STAFF ----------------
@app.route('/admin/login', methods=['GET','POST'])
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        admin = Admin.query.filter_by(username=request.form.get('username','').strip()).first()
        if admin and check_password_hash(admin.password_hash, request.form.get('password','')):
            session.clear(); session['admin_id'] = admin.id; session['admin_name'] = admin.username
            return redirect(url_for('dashboard'))
        flash('Tên đăng nhập hoặc mật khẩu chưa chính xác.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('member_login'))

@app.route('/dashboard')
@admin_required
def dashboard():
    customers = Customer.query.count()
    points = db.session.query(db.func.coalesce(db.func.sum(Customer.points),0)).scalar()
    revenue = db.session.query(db.func.coalesce(db.func.sum(Customer.total_spent),0)).scalar()
    tx_count = Transaction.query.count()
    recent = Transaction.query.order_by(Transaction.created_at.desc()).limit(7).all()
    top = Customer.query.order_by(Customer.points.desc()).limit(5).all()
    pending_orders = SaleOrder.query.filter_by(status='pending').count()
    return render_template('dashboard.html', customers=customers, points=points, revenue=revenue, tx_count=tx_count, recent=recent, top=top, pending_orders=pending_orders)

@app.route('/customers')
@admin_required
def customers():
    q = request.args.get('q','').strip(); query = Customer.query
    if q: query = query.filter(db.or_(Customer.name.ilike(f'%{q}%'), Customer.phone.ilike(f'%{q}%')))
    return render_template('customers.html', customers=query.order_by(Customer.created_at.desc()).all(), q=q)

@app.route('/customers/new', methods=['POST'])
@admin_required
def customer_new():
    name, phone = request.form.get('name','').strip(), request.form.get('phone','').strip()
    if not name or not phone: flash('Vui lòng nhập tên và số điện thoại.', 'error')
    elif Customer.query.filter_by(phone=phone).first(): flash('Số điện thoại này đã tồn tại.', 'error')
    else:
        db.session.add(Customer(name=name, phone=phone, email=request.form.get('email','').strip() or None)); db.session.commit()
        flash('Đã thêm khách hàng. Khách có thể đăng ký tài khoản bằng số điện thoại này sau khi được xác minh tại quầy.', 'success')
    return redirect(url_for('customers'))

@app.route('/customers/<int:customer_id>')
@admin_required
def customer_detail(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    transactions = Transaction.query.filter_by(customer_id=customer.id).order_by(Transaction.created_at.desc()).limit(50).all()
    return render_template('customer_detail.html', customer=customer, transactions=transactions)

@app.route('/customers/<int:customer_id>/earn', methods=['POST'])
@admin_required
def earn_points(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    try:
        amount = int(request.form.get('amount','0')); rate = max(1,int(setting('point_rate','10000')))
        if amount <= 0: raise ValueError
        earned = amount // rate
        if earned < 1: flash(f'Hóa đơn cần tối thiểu {rate:,}đ để được cộng 1 điểm.', 'error')
        else:
            customer.points += earned; customer.total_spent += amount
            db.session.add(Transaction(customer_id=customer.id,kind='earn',points=earned,amount=amount,note=request.form.get('note','').strip() or 'Tích điểm thủ công'))
            db.session.commit(); flash(f'Đã cộng {earned} điểm cho {customer.name}.', 'success')
    except ValueError: flash('Số tiền không hợp lệ.', 'error')
    return redirect(url_for('customer_detail',customer_id=customer.id))

@app.route('/customers/<int:customer_id>/adjust', methods=['POST'])
@admin_required
def adjust_points(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    try:
        delta = int(request.form.get('points','0'))
        if not delta or customer.points + delta < 0: raise ValueError
        customer.points += delta
        db.session.add(Transaction(customer_id=customer.id,kind='adjustment',points=delta,note=request.form.get('note','').strip() or 'Điều chỉnh bởi quản trị viên'))
        db.session.commit(); flash('Đã cập nhật điểm.', 'success')
    except ValueError: flash('Số điểm không hợp lệ hoặc số dư không đủ.', 'error')
    return redirect(url_for('customer_detail',customer_id=customer.id))

@app.route('/pos', methods=['GET','POST'])
@admin_required
def pos():
    if request.method == 'POST':
        try:
            raw_token = request.form.get('member_token','').strip()
            if raw_token.startswith('ATL-MEMBER:'): raw_token = raw_token.split(':',1)[1]
            customer = Customer.query.filter_by(member_token=raw_token).first()
            if not customer:
                phone = request.form.get('phone','').strip()
                customer = Customer.query.filter_by(phone=phone).first() if phone else None
            amount = int(request.form.get('amount','0'))
            if not customer or amount <= 0: raise ValueError
            order = SaleOrder(order_code='ATL-' + secrets.token_hex(4).upper(), customer_id=customer.id, amount=amount,
                              payment_method=request.form.get('payment_method','MoMo/VietQR'), payment_note=request.form.get('payment_note','').strip())
            db.session.add(order); db.session.commit()
            flash(f'Đã tạo hóa đơn {order.order_code}. Hãy kiểm tra tiền về rồi xác nhận thanh toán để cộng điểm.', 'success')
            return redirect(url_for('orders'))
        except ValueError: flash('Không tìm thấy hội viên hoặc số tiền không hợp lệ.', 'error')
    return render_template('pos.html', customers=Customer.query.order_by(Customer.name).all())

@app.route('/orders')
@admin_required
def orders():
    rows = SaleOrder.query.order_by(SaleOrder.created_at.desc()).limit(100).all()
    return render_template('orders.html', orders=rows)

@app.route('/orders/<int:order_id>/confirm', methods=['POST'])
@admin_required
def confirm_order(order_id):
    order = SaleOrder.query.get_or_404(order_id)
    if order.status != 'pending':
        flash('Hóa đơn này đã được xử lý, không thể cộng điểm lần nữa.', 'error')
        return redirect(url_for('orders'))
    rate = max(1,int(setting('point_rate','10000'))); earned = order.amount // rate
    if earned < 1:
        flash(f'Hóa đơn dưới mức tối thiểu {rate:,}đ nên không phát sinh điểm.', 'error')
        return redirect(url_for('orders'))
    # Change order status and create the ledger transaction in the same DB commit.
    order.status = 'paid'; order.paid_at = datetime.utcnow(); order.points_awarded = earned
    order.customer.points += earned; order.customer.total_spent += order.amount
    db.session.add(Transaction(customer_id=order.customer_id,kind='earn',points=earned,amount=order.amount,note=f'Đơn {order.order_code} · {order.payment_method}'))
    db.session.commit()
    flash(f'Đã xác nhận {order.order_code} và cộng {earned} điểm cho {order.customer.name}.', 'success')
    return redirect(url_for('orders'))

@app.route('/orders/<int:order_id>/cancel', methods=['POST'])
@admin_required
def cancel_order(order_id):
    order = SaleOrder.query.get_or_404(order_id)
    if order.status == 'pending': order.status = 'cancelled'; db.session.commit(); flash('Đã hủy hóa đơn chờ thanh toán.', 'success')
    else: flash('Chỉ có thể hủy hóa đơn đang chờ xác nhận.', 'error')
    return redirect(url_for('orders'))

@app.route('/api/member/<token>')
@admin_required
def api_member(token):
    c = Customer.query.filter_by(member_token=token).first()
    if not c: return jsonify({'found':False}),404
    return jsonify({'found':True,'id':c.id,'name':c.name,'phone':c.phone,'points':c.points})

@app.route('/vouchers')
@admin_required
def vouchers():
    rows = Voucher.query.order_by(Voucher.id.desc()).all()
    redemptions = Redemption.query.order_by(Redemption.created_at.desc()).limit(10).all()
    return render_template('vouchers.html',vouchers=rows,redemptions=redemptions,customers=Customer.query.order_by(Customer.name).all())

@app.route('/vouchers/new', methods=['POST'])
@admin_required
def voucher_new():
    try:
        name=request.form.get('name','').strip(); cost=int(request.form.get('points_cost','0')); qty=int(request.form.get('quantity','0'))
        if not name or cost<=0 or qty<0: raise ValueError
        db.session.add(Voucher(name=name,description=request.form.get('description','').strip(),points_cost=cost,quantity=qty)); db.session.commit(); flash('Đã tạo voucher.','success')
    except ValueError: flash('Thông tin voucher không hợp lệ.','error')
    return redirect(url_for('vouchers'))

@app.route('/vouchers/<int:voucher_id>/toggle',methods=['POST'])
@admin_required
def voucher_toggle(voucher_id):
    v=Voucher.query.get_or_404(voucher_id); v.active=not v.active; db.session.commit(); return redirect(url_for('vouchers'))

@app.route('/redeem',methods=['POST'])
@admin_required
def redeem():
    try:
        customer=Customer.query.get_or_404(int(request.form.get('customer_id','0'))); voucher=Voucher.query.get_or_404(int(request.form.get('voucher_id','0')))
        if not voucher.active or voucher.quantity<1 or customer.points<voucher.points_cost: raise ValueError
        code='ATL-'+secrets.token_hex(4).upper(); customer.points-=voucher.points_cost; voucher.quantity-=1
        db.session.add(Transaction(customer_id=customer.id,kind='redeem',points=-voucher.points_cost,note=f'Đổi voucher: {voucher.name}'))
        db.session.add(Redemption(customer_id=customer.id,voucher_id=voucher.id,code=code)); db.session.commit(); flash(f'Đổi thưởng thành công! Mã: {code}','success')
    except (ValueError,TypeError): flash('Không thể đổi voucher.','error')
    return redirect(url_for('vouchers'))

@app.route('/settings',methods=['GET','POST'])
@admin_required
def settings():
    if request.method=='POST':
        try:
            rate=int(request.form.get('point_rate','0'))
            if rate<1: raise ValueError
            row=Setting.query.filter_by(key='point_rate').first()
            if not row: db.session.add(Setting(key='point_rate',value=str(rate)))
            else: row.value=str(rate)
            db.session.commit(); flash('Đã lưu cấu hình tích điểm.','success')
        except ValueError: flash('Tỷ lệ phải là số nguyên lớn hơn 0.','error')
    return render_template('settings.html',rate=setting('point_rate','10000'))

# ---------------- CUSTOMER PORTAL ----------------
@app.route('/member/register',methods=['GET','POST'])
def member_register():
    if request.method=='POST':
        name=request.form.get('name','').strip(); phone=request.form.get('phone','').strip(); password=request.form.get('password','')
        if len(password)<8: flash('Mật khẩu phải có ít nhất 8 ký tự.','error')
        elif not name or not phone: flash('Vui lòng nhập họ tên và số điện thoại.','error')
        elif Customer.query.filter_by(phone=phone).first(): flash('Số điện thoại đã có tài khoản hoặc đã được tạo tại quầy. Vui lòng đăng nhập hoặc liên hệ nhân viên để hỗ trợ kích hoạt.','error')
        else:
            c=Customer(name=name,phone=phone,password_hash=generate_password_hash(password)); db.session.add(c); db.session.commit()
            session.clear(); session['customer_id']=c.id; session['customer_name']=c.name
            flash('Chào mừng bạn đến với AnTumLum!','success'); return redirect(url_for('member_home'))
    return render_template('member_auth.html',mode='register')

@app.route('/member/login',methods=['GET','POST'])
def member_login():
    if request.method=='POST':
        c=Customer.query.filter_by(phone=request.form.get('phone','').strip()).first()
        if c and c.password_hash and check_password_hash(c.password_hash,request.form.get('password','')):
            session.clear(); session['customer_id']=c.id; session['customer_name']=c.name
            return redirect(request.args.get('next') or url_for('member_home'))
        flash('Số điện thoại hoặc mật khẩu không đúng.','error')
    return render_template('member_auth.html',mode='login')

@app.route('/member/logout')
def member_logout():
    session.pop('customer_id',None); session.pop('customer_name',None); return redirect(url_for('member_login'))

@app.route('/member')
@member_required
def member_home():
    c=Customer.query.get_or_404(session['customer_id'])
    transactions=Transaction.query.filter_by(customer_id=c.id).order_by(Transaction.created_at.desc()).limit(20).all()
    redemptions=Redemption.query.filter_by(customer_id=c.id).order_by(Redemption.created_at.desc()).limit(10).all()
    vouchers=Voucher.query.filter_by(active=True).filter(Voucher.quantity>0).order_by(Voucher.points_cost).all()
    return render_template('member_home.html',customer=c,transactions=transactions,redemptions=redemptions,vouchers=vouchers)

@app.route('/join-qr.png')
def join_qr():
    """Public shop QR: sends new customers to the member registration page."""
    import qrcode
    target = request.url_root.rstrip('/') + url_for('member_register')
    img = qrcode.make(target); out = io.BytesIO(); img.save(out, format='PNG')
    return app.response_class(out.getvalue(), mimetype='image/png', headers={'Cache-Control':'no-store'})

@app.route('/member/qr.png')
@member_required
def member_qr():
    import qrcode
    c=Customer.query.get_or_404(session['customer_id'])
    payload='ATL-MEMBER:'+c.member_token
    img=qrcode.make(payload); out=io.BytesIO(); img.save(out,format='PNG')
    return app.response_class(out.getvalue(),mimetype='image/png',headers={'Cache-Control':'no-store'})

@app.route('/member/redeem/<int:voucher_id>',methods=['POST'])
@member_required
def member_redeem(voucher_id):
    c=Customer.query.get_or_404(session['customer_id']); v=Voucher.query.get_or_404(voucher_id)
    if not v.active or v.quantity<1 or c.points<v.points_cost:
        flash('Bạn chưa đủ điểm hoặc voucher đã hết.','error'); return redirect(url_for('member_home'))
    code='ATL-'+secrets.token_hex(4).upper(); c.points-=v.points_cost; v.quantity-=1
    db.session.add(Transaction(customer_id=c.id,kind='redeem',points=-v.points_cost,note=f'Đổi voucher: {v.name}'))
    db.session.add(Redemption(customer_id=c.id,voucher_id=v.id,code=code)); db.session.commit()
    flash(f'Đổi voucher thành công! Mã voucher của bạn: {code}','success'); return redirect(url_for('member_home'))

# DB initialization and lightweight migration for existing SQLite/Postgres deployments.
def initialize():
    with app.app_context():
        db.create_all()
        # create_all does not add columns to an existing Customer table.
        inspector=inspect(db.engine)
        cols={c['name'] for c in inspector.get_columns('customer')}
        dialect=db.engine.dialect.name
        additions=[]
        if 'password_hash' not in cols: additions.append('ALTER TABLE customer ADD COLUMN password_hash VARCHAR(255)')
        if 'member_token' not in cols: additions.append('ALTER TABLE customer ADD COLUMN member_token VARCHAR(64)')
        for sql in additions: db.session.execute(text(sql))
        db.session.commit()
        # Enforce uniqueness for member QR tokens on both SQLite and PostgreSQL.
        db.session.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_customer_member_token ON customer (member_token)'))
        db.session.commit()
        # Populate unique member tokens for existing customers.
        for c in Customer.query.filter((Customer.member_token.is_(None)) | (Customer.member_token=='')).all(): c.member_token=secrets.token_urlsafe(24)
        if not Admin.query.filter_by(username='admin').first():
            db.session.add(Admin(username='admin',password_hash=generate_password_hash(os.environ.get('ADMIN_PASSWORD','admin12345'))))
        if not Setting.query.filter_by(key='point_rate').first(): db.session.add(Setting(key='point_rate',value='10000'))
        if Voucher.query.count()==0:
            db.session.add_all([Voucher(name='Giảm 10.000đ',description='Áp dụng cho đơn tiếp theo',points_cost=100,quantity=30),Voucher(name='Tặng topping',description='Một phần topping tùy chọn',points_cost=60,quantity=50),Voucher(name='Giảm 20.000đ',description='Áp dụng cho đơn từ 50.000đ',points_cost=180,quantity=20)])
        db.session.commit()

initialize()
if __name__=='__main__': app.run(debug=os.environ.get('FLASK_DEBUG')=='1')
