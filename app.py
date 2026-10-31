"""Brightloop Subscription Management System.  Run: pip install flask && python app.py  ->  http://localhost:5000
Demo logins (password Demo@12345): admin@brightloop.com, staff@brightloop.com, customer@brightloop.com"""
import sqlite3, re, time, secrets, random, calendar, datetime as dt
from flask import Flask, request, jsonify, session, g, abort
from werkzeug.security import generate_password_hash as H, check_password_hash as C

app = Flask(__name__, static_folder='static', static_url_path='/static'); app.secret_key = 'brightloop-hackathon'
D = dt.date; TD = lambda n=0: (D.today() + dt.timedelta(days=n)).isoformat()
SCHEMA = '''
create table if not exists users(id integer primary key,email text unique,pw text,role text,name text);
create table if not exists resets(token text,email text);
create table if not exists inbox(id integer primary key,to_email text,subject text,body text,created text);
create table if not exists taxes(id integer primary key,name text,rate real);
create table if not exists products(id integer primary key,name text,type text,price real,cost real,notes text,attribute text,variants text);
create table if not exists plans(id integer primary key,name text,price real,freq text,min_qty integer default 1,avail_from text,avail_to text,auto_close integer default 0,allow_early_close integer default 0,allow_pause integer default 0,allow_renew integer default 0);
create table if not exists templates(id integer primary key,name text,plan_id integer,product_id integer,variant text,qty integer,validity_days integer);
create table if not exists discounts(id integer primary key,name text,type text,value real,min_amount real,min_qty integer,d_from text,d_to text,max_uses integer,used_count integer default 0,scope text,product_id integer);
create table if not exists subs(id integer primary key,number text,customer_id integer,plan_id integer,start_date text,expiry text,next_billing text,terms text,status text,tax_id integer,valid_until text);
create table if not exists sub_lines(id integer primary key,sub_id integer,product_id integer,variant text,qty integer,unit_price real);
create table if not exists invoices(id integer primary key,number text,sub_id integer,customer_id integer,status text,issue_date text,due_date text,ps text,pe text,subtotal real,discount real,tax real,total real,paid real default 0,unique(sub_id,ps,pe));
create table if not exists inv_lines(id integer primary key,inv_id integer,descr text,qty integer,unit_price real,amount real);
create table if not exists payments(id integer primary key,inv_id integer,method text,amount real,date text,note text);
create index if not exists ix_sub_status_next on subs(status,next_billing);
create index if not exists ix_sub_cust on subs(customer_id);
create index if not exists ix_inv_status_due on invoices(status,due_date);
create index if not exists ix_inv_cust on invoices(customer_id);
create index if not exists ix_sl on sub_lines(sub_id);
'''
CAT = {'products': 'name type price cost notes attribute variants',
       'plans': 'name price freq min_qty avail_from avail_to auto_close allow_early_close allow_pause allow_renew',
       'taxes': 'name rate', 'discounts': 'name type value min_amount min_qty d_from d_to max_uses scope product_id',
       'templates': 'name plan_id product_id variant qty validity_days'}

def db():
    if 'db' not in g: g.db = sqlite3.connect('brightloop.db'); g.db.row_factory = sqlite3.Row
    return g.db
@app.teardown_appcontext
def _close(e):
    c = g.pop('db', None)
    if c: c.close()
def q(s, a=()): return [dict(r) for r in db().execute(s, a).fetchall()]
def one(s, a=()): r = q(s, a); return r[0] if r else None
def ex(s, a=()): c = db().execute(s, a); db().commit(); return c.lastrowid
def fail(m, c=400): r = jsonify(error=m); r.status_code = c; abort(r)
def need(*roles):
    u = one('select * from users where id=?', (session.get('uid'),))
    if not u: fail('Login required', 401)
    if roles and u['role'] not in roles: fail('Not allowed for your role', 403)
    return u
def mail(to, sub, body): ex('insert into inbox(to_email,subject,body,created) values(?,?,?,?)', (to, sub, body, dt.datetime.now().isoformat(timespec='seconds')))
def adv(d, f, n=1):
    x = D.fromisoformat(d)
    if f == 'Daily': return (x + dt.timedelta(days=n)).isoformat()
    if f == 'Weekly': return (x + dt.timedelta(weeks=n)).isoformat()
    y, m = divmod(x.month - 1 + (n if f == 'Monthly' else 12 * n), 12); y += x.year
    return x.replace(year=y, month=m + 1, day=min(x.day, calendar.monthrange(y, m + 1)[1])).isoformat()

@app.before_request
def _t0(): g.t = time.perf_counter()
@app.after_request
def _t1(r): r.headers['X-Query-Ms'] = str(round((time.perf_counter() - g.t) * 1000)); return r
@app.get('/')
def home(): return app.send_static_file('index.html')

# ---------- Module A: auth & RBAC ----------
def okpw(p): return len(p) > 8 and re.search('[A-Z]', p) and re.search('[a-z]', p) and re.search('[^A-Za-z0-9]', p)
def mkuser(email, pw, role, name):
    email = (email or '').strip().lower()
    if not re.match(r'[^@\s]+@[^@\s]+\.\w+$', email): fail('Enter a valid email')
    if not okpw(pw or ''): fail('Password needs 9+ characters with an uppercase letter, a lowercase letter and a special character')
    if one('select 1 x from users where email=?', (email,)): fail('This email already has an account', 409)
    return ex('insert into users(email,pw,role,name) values(?,?,?,?)', (email, H(pw), role, name or email.split('@')[0]))
@app.post('/api/signup')
def signup(): d = request.json; session['uid'] = mkuser(d.get('email'), d.get('password'), 'customer', d.get('name')); return jsonify(ok=1)
@app.post('/api/login')
def login():
    d = request.json; u = one('select * from users where email=?', ((d.get('email') or '').strip().lower(),))
    if not u or not C(u['pw'], d.get('password') or ''): fail('Wrong email or password', 401)
    session['uid'] = u['id']; return jsonify(ok=1)
@app.post('/api/demo/<role>')
def demo(role):
    u = one('select id from users where email=?', (f'{role}@brightloop.com',))
    if not u: fail('Unknown demo role', 404)
    session['uid'] = u['id']; return jsonify(ok=1)
@app.post('/api/logout')
def logout(): session.clear(); return jsonify(ok=1)
@app.get('/api/me')
def me(): u = need(); return jsonify({k: u[k] for k in ('id', 'email', 'name', 'role')})
@app.post('/api/forgot')
def forgot():
    e = (request.json.get('email') or '').strip().lower()
    if one('select 1 x from users where email=?', (e,)):
        t = secrets.token_urlsafe(16); ex('insert into resets values(?,?)', (t, e)); mail(e, 'Reset your Brightloop password', f'Use this link to set a new password: /#reset={t}')
    return jsonify(ok=1)
@app.post('/api/reset')
def reset():
    d = request.json; r = one('select * from resets where token=?', (d.get('token'),))
    if not r: fail('This reset link is invalid or already used')
    if not okpw(d.get('password') or ''): fail('Password needs 9+ characters with an uppercase letter, a lowercase letter and a special character')
    ex('update users set pw=? where email=?', (H(d['password']), r['email'])); ex('delete from resets where token=?', (d['token'],)); return jsonify(ok=1)
@app.get('/api/inbox')
def inbox(): return jsonify(q('select * from inbox order by id desc limit 20'))
@app.post('/api/staff')
def staff(): need('admin'); d = request.json; return jsonify(id=mkuser(d.get('email'), d.get('password'), 'staff', d.get('name')))
@app.get('/api/users')
def users(): need('admin', 'staff'); return jsonify(q("select id,email,name,role from users where email not like 'bulk%' order by id"))

# ---------- Modules B & D: catalog (products, plans, taxes, discounts, templates) ----------
@app.get('/api/cat/<t>')
def cat_list(t):
    u = need()
    if t not in CAT: abort(404)
    if u['role'] == 'customer' and t not in ('products', 'plans'): fail('Not allowed', 403)
    return jsonify(q(f'select * from {t} order by id desc limit 200'))
@app.post('/api/cat/<t>')
def cat_add(t):
    need('admin')
    if t not in CAT: abort(404)
    d = request.json; cols = CAT[t].split()
    return jsonify(id=ex(f'insert into {t}({",".join(cols)}) values({",".join("?" * len(cols))})', [d.get(c) for c in cols]))

# ---------- Module C: subscriptions & state machine ----------
def uprice(pid, var):
    p = one('select * from products where id=?', (pid,))
    if not p: fail('Product not found', 404)
    x = dict(v.split('=') for v in (p['variants'] or '').split(';') if '=' in v)
    return p['price'] + float(x.get(var or '', 0))
def add_sub(cust, plan_id, start, lines, st='Draft', tax=1, terms='Net 15', valid=None):
    pl = one('select * from plans where id=?', (plan_id,))
    if not pl: fail('Plan not found', 404)
    for l in lines:
        if int(l['qty']) < pl['min_qty']: fail(f"{pl['name']} needs a minimum quantity of {pl['min_qty']}")
    n = one('select count(*) n from subs')['n'] + 1
    sid = ex('insert into subs(number,customer_id,plan_id,start_date,expiry,next_billing,terms,status,tax_id,valid_until) values(?,?,?,?,?,?,?,?,?,?)',
             (f'SUB-{D.today().year}-{n:04d}', cust, plan_id, start, adv(start, 'Yearly'), start, terms, st, tax, valid))
    for l in lines: ex('insert into sub_lines(sub_id,product_id,variant,qty,unit_price) values(?,?,?,?,?)', (sid, l['product_id'], l.get('variant') or '', l['qty'], uprice(l['product_id'], l.get('variant'))))
    return sid
@app.post('/api/subs')
def sub_new():
    need('admin', 'staff'); d = request.json; plan = d.get('plan_id'); lines = d.get('lines') or []; st = 'Draft'; valid = None
    if d.get('template_id'):
        T = one('select * from templates where id=?', (d['template_id'],))
        if not T: fail('Template not found', 404)
        plan = T['plan_id']; lines = [dict(product_id=T['product_id'], variant=T['variant'], qty=T['qty'])]; st = 'Quotation'; valid = TD(T['validity_days'] or 30)
    if not (d.get('customer_id') and plan and lines): fail('Choose a customer, a plan and at least one line')
    return jsonify(id=add_sub(d['customer_id'], plan, d.get('start_date') or TD(), lines, st, d.get('tax_id') or 1, d.get('terms') or 'Net 15', valid))
@app.get('/api/subs')
def subs_list():
    u = need(); a = request.args; w = ['1']; p = []
    if u['role'] == 'customer': w.append('s.customer_id=?'); p.append(u['id'])
    for k in ('status', 'plan_id'):
        if a.get(k): w.append(f's.{k}=?'); p.append(a[k])
    W = ' and '.join(w); pg = max(int(a.get('page', 1)), 1)
    rows = q(f'select s.*,u.name cust,p.name plan,p.freq,(select sum(qty*unit_price) from sub_lines where sub_id=s.id) amount from subs s join users u on u.id=s.customer_id join plans p on p.id=s.plan_id where {W} order by s.id desc limit 25 offset ?', p + [(pg - 1) * 25])
    return jsonify(rows=rows, total=one(f'select count(*) n from subs s where {W}', p)['n'])
def sub_get(i):
    u = need()
    s = one('select s.*,u.name cust,p.name plan,p.freq,p.allow_pause,p.allow_early_close ec,p.allow_renew,p.min_qty,(select rate from taxes where id=s.tax_id) rate from subs s join users u on u.id=s.customer_id join plans p on p.id=s.plan_id where s.id=?', (i,))
    if not s or (u['role'] == 'customer' and s['customer_id'] != u['id']): fail('Subscription not found', 404)
    return u, s
@app.get('/api/subs/<int:i>')
def sub_detail(i):
    u, s = sub_get(i)
    s['lines'] = q('select l.*,p.name,l.qty*l.unit_price amount from sub_lines l join products p on p.id=l.product_id where sub_id=?', (i,))
    s['invoices'] = q('select id,number,status,total,paid,due_date from invoices where sub_id=? order by id desc limit 20', (i,))
    s['addons'] = q("select id,name,price from products where type='Add-on'")
    return jsonify(s)
TR = {'quote': ({'Draft'}, 'Quotation'), 'confirm': ({'Quotation'}, 'Confirmed'), 'activate': ({'Confirmed'}, 'Active'), 'pause': ({'Active'}, 'Paused'),
      'resume': ({'Paused'}, 'Active'), 'close': ({'Active', 'Paused'}, 'Closed'), 'renew': ({'Active'}, 'Active')}
@app.post('/api/subs/<int:i>/addon')
def addon(i):
    u, s = sub_get(i); d = request.json
    if s['status'] == 'Closed': fail('This subscription is closed')
    if not one("select 1 x from products where id=? and type='Add-on'", (d['product_id'],)): fail('Not an add-on')
    ex('delete from sub_lines where sub_id=? and product_id=?', (i, d['product_id']))
    if d.get('on'): ex('insert into sub_lines(sub_id,product_id,variant,qty,unit_price) values(?,?,?,?,?)', (i, d['product_id'], '', s['min_qty'], uprice(d['product_id'], '')))
    return jsonify(ok=1)
@app.post('/api/subs/<int:i>/<act>')
def sub_act(i, act):
    u, s = sub_get(i)
    if act not in TR: fail('Unknown action')
    if u['role'] == 'customer' and act not in ('pause', 'resume', 'close', 'renew'): fail('Not allowed', 403)
    fr, to = TR[act]
    if s['status'] not in fr: fail(f"A {s['status']} subscription cannot be changed with '{act}'")
    if (act == 'pause' and not s['allow_pause']) or (act == 'close' and not s['ec']) or (act == 'renew' and not s['allow_renew']): fail('This action is not enabled on the subscription plan')
    if act == 'renew': ex('update subs set expiry=? where id=?', (adv(s['expiry'], 'Yearly'), i))
    else: ex('update subs set status=? where id=?', (to, i))
    return jsonify(ok=1)

# ---------- Module E: billing day engine ----------
def disc_for(L, ds, t):
    out = []
    for d in ds:
        if (d['d_from'] and d['d_from'] > t) or (d['d_to'] and d['d_to'] < t) or (d['max_uses'] and d['used_count'] >= d['max_uses']): continue
        ls = L if d['scope'] != 'Product' else [l for l in L if l['product_id'] == d['product_id']]
        base = sum(l['qty'] * l['unit_price'] for l in ls); n = sum(l['qty'] for l in ls)
        if not ls or base < (d['min_amount'] or 0) or n < (d['min_qty'] or 0): continue
        out.append((d, round(min(base, base * d['value'] / 100 if d['type'] == 'Percentage' else d['value']), 2)))
    return out
@app.post('/api/billing/run')
def billing():
    need('admin', 'staff'); c = db(); t = TD(); gen = skip = nd = 0
    c.execute("update subs set status='Closed' where status='Active' and expiry<? and plan_id in (select id from plans where auto_close=1)", (t,))
    ds = q('select * from discounts')
    for s in q("select s.*,p.freq,p.auto_close,coalesce(x.rate,0) rate from subs s join plans p on p.id=s.plan_id left join taxes x on x.id=s.tax_id where s.status='Active' and s.next_billing<=?", (t,)):
        ps = s['next_billing']; nx = adv(ps, s['freq']); pe = (D.fromisoformat(nx) - dt.timedelta(1)).isoformat()
        L = q('select l.*,p.name from sub_lines l join products p on p.id=l.product_id where sub_id=?', (s['id'],))
        sub = sum(l['qty'] * l['unit_price'] for l in L); ap = disc_for(L, ds, t); dis = min(sub, sum(a for _, a in ap)); tax = round((sub - dis) * s['rate'] / 100, 2)
        due = TD(int(re.sub(r'\D', '', s['terms'] or '') or 0))
        try:  # unique(sub_id, ps, pe) is the idempotency guard: a period can never be billed twice
            iid = c.execute('insert into invoices(number,sub_id,customer_id,status,issue_date,due_date,ps,pe,subtotal,discount,tax,total,paid) values(?,?,?,?,?,?,?,?,?,?,?,?,0)',
                            ('', s['id'], s['customer_id'], 'Draft', t, due, ps, pe, sub, dis, tax, round(sub - dis + tax, 2))).lastrowid
        except sqlite3.IntegrityError: skip += 1
        else:
            c.execute('update invoices set number=? where id=?', (f'INV-{D.today().year}-{iid:05d}', iid))
            c.executemany('insert into inv_lines(inv_id,descr,qty,unit_price,amount) values(?,?,?,?,?)', [(iid, l['name'] + (f" ({l['variant']})" if l['variant'] else ''), l['qty'], l['unit_price'], l['qty'] * l['unit_price']) for l in L])
            for d, a in ap: c.execute('update discounts set used_count=used_count+1 where id=?', (d['id'],)); d['used_count'] += 1; nd += 1
            gen += 1
        c.execute('update subs set next_billing=?,status=? where id=?', (nx, 'Closed' if s['auto_close'] and nx > s['expiry'] else 'Active', s['id']))
    c.commit(); return jsonify(generated=gen, skipped=skip, discounts=nd)

# ---------- Invoices & payments (Module F) ----------
def INV(): return f"select i.*,u.name cust,case when i.status='Confirmed' and i.due_date<'{TD()}' then 'Overdue' else i.status end st from invoices i join users u on u.id=i.customer_id"
@app.get('/api/invoices')
def inv_list():
    u = need(); a = request.args; w = ['1']; p = []; s = a.get('status')
    if u['role'] == 'customer': w.append('i.customer_id=?'); p.append(u['id'])
    if s == 'Overdue': w.append(f"i.status='Confirmed' and i.due_date<'{TD()}'")
    elif s: w.append('i.status=?'); p.append(s)
    W = ' and '.join(w); pg = max(int(a.get('page', 1)), 1)
    return jsonify(rows=q(f'{INV()} where {W} order by i.id desc limit 25 offset ?', p + [(pg - 1) * 25]), total=one(f'select count(*) n from invoices i where {W}', p)['n'])
def inv_get(i):
    u = need(); r = one(INV() + ' where i.id=?', (i,))
    if not r or (u['role'] == 'customer' and r['customer_id'] != u['id']): fail('Invoice not found', 404)
    r['lines'] = q('select * from inv_lines where inv_id=?', (i,)); r['payments'] = q('select * from payments where inv_id=? order by id', (i,)); return u, r
@app.get('/api/invoices/<int:i>')
def inv_detail(i): return jsonify(inv_get(i)[1])
@app.post('/api/invoices/confirm_all')
def confirm_all(): need('admin', 'staff'); ex("update invoices set status='Confirmed' where status='Draft'"); return jsonify(ok=1)
@app.post('/api/invoices/<int:i>/<act>')
def inv_act(i, act):
    u, r = inv_get(i); d = request.json or {}
    if u['role'] == 'customer': fail('Not allowed', 403)
    if act == 'confirm' and r['status'] == 'Draft': ex("update invoices set status='Confirmed' where id=?", (i,))
    elif act == 'cancel' and r['status'] in ('Draft', 'Confirmed') and not r['paid']: ex("update invoices set status='Cancelled' where id=?", (i,))
    elif act == 'send': mail(one('select email from users where id=?', (r['customer_id'],))['email'], f"Invoice {r['number']}", f"Total {r['total']:.2f}, due {r['due_date']}. Open /invoice/{i}/print")
    elif act == 'pay' and r['status'] == 'Confirmed':
        amt = round(float(d.get('amount') or 0), 2)
        if amt <= 0 or amt > round(r['total'] - r['paid'], 2) + 0.005: fail('Amount must be above 0 and not more than the outstanding balance')
        ex('insert into payments(inv_id,method,amount,date,note) values(?,?,?,?,?)', (i, d.get('method', 'Bank Transfer'), amt, d.get('date') or TD(), d.get('note', '')))
        ex("update invoices set paid=paid+?,status=case when paid+?>=total-0.005 then 'Paid' else status end where id=?", (amt, amt, i))
    else: fail(f"You cannot {act} an invoice that is {r['status']}")
    return jsonify(ok=1)
@app.get('/invoice/<int:i>/print')
def prn(i):
    r = inv_get(i)[1]; c = one('select name,email from users where id=?', (r['customer_id'],))
    rows = ''.join(f"<tr><td>{l['descr']}</td><td>{l['qty']}</td><td>{l['unit_price']:.2f}</td><td>{l['amount']:.2f}</td></tr>" for l in r['lines'])
    return f"""<html><title>{r['number']}</title><style>body{{font:14px sans-serif;max-width:720px;margin:30px auto}}td,th{{border-bottom:1px solid #ddd;padding:6px;text-align:left}}table{{width:100%;border-collapse:collapse}}@media print{{button{{display:none}}}}</style>
<button onclick="print()">Print / Save as PDF</button><h1 style="color:#714B67">Brightloop Software</h1><h2>Invoice {r['number']} ({r['st']})</h2>
<p>Billed to <b>{c['name']}</b> ({c['email']})<br>Issued {r['issue_date']}, due {r['due_date']}, period {r['ps']} to {r['pe']}</p>
<table><tr><th>Item</th><th>Qty</th><th>Unit</th><th>Amount</th></tr>{rows}</table>
<p style="text-align:right">Subtotal {r['subtotal']:.2f}<br>Discount -{r['discount']:.2f}<br>Tax {r['tax']:.2f}<br><b>Total {r['total']:.2f}</b><br>Paid {r['paid']:.2f}, balance {r['total'] - r['paid']:.2f}</p></html>"""

@app.get('/api/dashboard')
def dash():
    need('admin', 'staff'); a = request.args; t = TD(); bw = ['1']; bp = []
    for k, col in (('plan_id', 'pl.id'), ('freq', 'pl.freq')):
        if a.get(k): bw.append(f'{col}=?'); bp.append(a[k])
    iw = list(bw); ip = list(bp)
    if a.get('frm'): iw.append('i.issue_date>=?'); ip.append(a['frm'])
    if a.get('to'): iw.append('i.issue_date<=?'); ip.append(a['to'])
    s = a.get('status')
    if s == 'Overdue': iw.append(f"i.status='Confirmed' and i.due_date<'{t}'")
    elif s: iw.append('i.status=?'); ip.append(s)
    B = ' and '.join(bw); I = ' and '.join(iw); J = 'from invoices i join subs s on s.id=i.sub_id join plans pl on pl.id=s.plan_id where '
    m = "case pl.freq when 'Daily' then 30 when 'Weekly' then 4.345 when 'Monthly' then 1 else 1/12.0 end"
    act = one(f"select count(*) n,coalesce(sum(a.amt*{m}),0) mrr from subs s join plans pl on pl.id=s.plan_id left join (select sub_id,sum(qty*unit_price) amt from sub_lines group by sub_id) a on a.sub_id=s.id where s.status='Active' and {B}", bp)
    k = one(f"select coalesce(sum(i.paid),0) rev,coalesce(sum(case when i.status='Confirmed' then i.total-i.paid end),0) owed,coalesce(sum(i.status='Confirmed' and i.due_date<'{t}'),0) od {J}{I}", ip)
    ch = q(f'select substr(i.issue_date,1,7) m,sum(i.total) billed,sum(i.paid) paid {J}{I} group by m order by m desc limit 12', ip)[::-1]
    st = q(f"select case when i.status='Confirmed' and i.due_date<'{t}' then 'Overdue' else i.status end st,count(*) n {J}{I} group by st", ip)
    return jsonify(active=act['n'], mrr=round(act['mrr'], 2), arr=round(act['mrr'] * 12, 2), **k, chart=ch, status=st)

# ---------- Seeder ----------
def bulk(n):
    c = db(); r = random; t = D.today()
    if not one("select 1 x from users where email like 'bulk%'"):
        h = H('Demo@12345'); c.executemany('insert into users(email,pw,role,name) values(?,?,?,?)', [(f'bulk{i}@example.com', h, 'customer', f'Customer {i:02d}') for i in range(40)])
    cu = [x['id'] for x in q("select id from users where email like 'bulk%'")]; pl = q('select * from plans'); pr = q("select * from products where type!='Add-on'"); k = one('select count(*) n from subs')['n']
    for _ in range(n):
        p = r.choice(pl); x = r.choice(pr); qty = max(p['min_qty'], r.randint(1, 12)); cid = r.choice(cu); k += 1
        sd = t - dt.timedelta(days=r.randint(30, 300))
        sid = c.execute('insert into subs(number,customer_id,plan_id,start_date,expiry,next_billing,terms,status,tax_id) values(?,?,?,?,?,?,?,?,?)',
                        (f'SUB-{t.year}-{k:04d}', cid, p['id'], sd.isoformat(), (sd + dt.timedelta(days=365)).isoformat(), (t + dt.timedelta(days=r.randint(-20, 30))).isoformat(), 'Net 15', r.choice(['Active'] * 7 + ['Paused', 'Closed', 'Draft']), r.choice([1, 2]))).lastrowid
        c.execute('insert into sub_lines(sub_id,product_id,variant,qty,unit_price) values(?,?,?,?,?)', (sid, x['id'], '', qty, x['price']))
        if r.random() < .6:
            sb = qty * x['price']; tot = round(sb * 1.18, 2); s2 = r.choice(['Paid', 'Paid', 'Confirmed', 'Confirmed', 'Draft']); ps = t - dt.timedelta(days=r.randint(5, 170))
            paid = tot if s2 == 'Paid' else (round(tot * r.choice([0, 0, .4]), 2) if s2 == 'Confirmed' else 0)
            i = c.execute('insert into invoices(number,sub_id,customer_id,status,issue_date,due_date,ps,pe,subtotal,discount,tax,total,paid) values(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                          (f'INV-B-{k:05d}', sid, cid, s2, ps.isoformat(), (ps + dt.timedelta(days=15)).isoformat(), ps.isoformat(), (ps + dt.timedelta(days=29)).isoformat(), sb, 0, round(tot - sb, 2), tot, paid)).lastrowid
            c.execute('insert into inv_lines(inv_id,descr,qty,unit_price,amount) values(?,?,?,?,?)', (i, x['name'], qty, x['price'], sb))
    c.commit()
def seed():
    c = db()
    if one('select count(*) n from users')['n']: return
    pw = H('Demo@12345')
    for e, r, n in [('admin', 'admin', 'Asha Admin'), ('staff', 'staff', 'Sam Staff'), ('customer', 'customer', 'Acme Retail'), ('globex', 'customer', 'Globex Corp'), ('initech', 'customer', 'Initech Ltd')]:
        c.execute('insert into users(email,pw,role,name) values(?,?,?,?)', (e + '@brightloop.com', pw, r, n))
    c.executemany('insert into taxes(name,rate) values(?,?)', [('GST 18%', 18), ('SaaS Tax 10%', 10)])
    c.executemany('insert into products(name,type,price,cost,notes,attribute,variants) values(?,?,?,?,?,?,?)', [('Brightloop CRM', 'Software', 1000, 400, 'Core suite', 'Brand', 'Brightloop=0;Odoo=560'), ('Support Desk', 'Service', 300, 120, '', '', ''), ('Extra Seats', 'Add-on', 50, 10, 'Per seat', '', ''), ('Analytics Pack', 'Add-on', 120, 30, '', '', '')])
    c.executemany('insert into plans(name,price,freq,min_qty,avail_from,avail_to,auto_close,allow_early_close,allow_pause,allow_renew) values(?,?,?,?,?,?,?,?,?,?)',
                  [('Starter Monthly', 99, 'Monthly', 1, '2026-01-01', '2027-12-31', 0, 1, 1, 1), ('Business Monthly', 499, 'Monthly', 5, '2026-01-01', '2027-12-31', 0, 1, 1, 1), ('Enterprise Yearly', 4999, 'Yearly', 10, '2026-01-01', '2027-12-31', 1, 0, 0, 1), ('Weekly Pilot', 29, 'Weekly', 1, '2026-01-01', '2027-12-31', 1, 1, 0, 0)])
    c.executemany('insert into discounts(name,type,value,min_amount,min_qty,d_from,d_to,max_uses,used_count,scope,product_id) values(?,?,?,?,?,?,?,?,?,?,?)',
                  [('SEATS10', 'Percentage', 10, 0, 5, '2026-01-01', '2027-12-31', 100, 0, 'Subscription', None), ('WELCOME500', 'Fixed Amount', 500, 2000, 0, '2026-01-01', '2027-12-31', 3, 0, 'Subscription', None), ('OLD20', 'Percentage', 20, 0, 0, '2025-01-01', '2025-12-31', 50, 0, 'Subscription', None)])
    c.executemany('insert into templates(name,plan_id,product_id,variant,qty,validity_days) values(?,?,?,?,?,?)', [('Starter Offer', 1, 1, 'Brightloop', 1, 15), ('Enterprise Offer (Odoo)', 3, 1, 'Odoo', 10, 30)])
    c.commit()
    L = lambda p, v, n: [dict(product_id=p, variant=v, qty=n)]
    def mk(cu, pl, lines, st, nb=None, start=-60):
        s = add_sub(cu, pl, TD(start), lines, st)
        if nb is not None: ex('update subs set next_billing=? where id=?', (TD(nb), s))
        return s
    def inv(s, cu, st, o, tot, paid, due):
        sb = round(tot / 1.18, 2)
        i = c.execute('insert into invoices(number,sub_id,customer_id,status,issue_date,due_date,ps,pe,subtotal,discount,tax,total,paid) values(?,?,?,?,?,?,?,?,?,0,?,?,?)', (f'INV-H{s}{abs(o)}', s, cu, st, TD(o), TD(due), TD(o), TD(o + 29), sb, round(tot - sb, 2), tot, paid)).lastrowid
        c.execute('insert into inv_lines(inv_id,descr,qty,unit_price,amount) values(?,?,1,?,?)', (i, 'Subscription charges', sb, sb))
    a = mk(3, 2, L(1, 'Odoo', 5) + L(3, '', 5), 'Active', 0)          # due today; SEATS10 applies
    b = mk(4, 3, L(1, 'Odoo', 10), 'Active', 0, -300)                  # yearly; SEATS10 + WELCOME500 apply
    mk(5, 1, L(1, 'Brightloop', 1), 'Active', -1)
    d2 = mk(3, 1, L(1, 'Brightloop', 1), 'Active', 0)                  # already billed for this period -> skipped by Billing Day
    ps = TD(); pe = (D.fromisoformat(adv(ps, 'Monthly')) - dt.timedelta(1)).isoformat()
    c.execute("insert into invoices(number,sub_id,customer_id,status,issue_date,due_date,ps,pe,subtotal,discount,tax,total,paid) values('INV-SEED-1',?,3,'Confirmed',?,?,?,?,1000,0,180,1180,0)", (d2, TD(), TD(15), ps, pe))
    mk(4, 1, L(2, '', 1), 'Paused', 10); mk(5, 2, L(4, '', 5), 'Quotation'); mk(3, 1, L(2, '', 2), 'Draft'); mk(5, 4, L(3, '', 3), 'Closed')
    inv(a, 3, 'Confirmed', -90, 5900, 0, -60); inv(a, 3, 'Confirmed', -60, 5900, 2000, -30); inv(a, 3, 'Paid', -120, 5900, 5900, -90); inv(b, 4, 'Confirmed', -45, 18000, 0, -10)
    c.commit(); bulk(500)

@app.post('/api/seed')
def seed_api(): need('admin', 'staff'); n = min(int((request.json or {}).get('n', 2000)), 5000); bulk(n); return jsonify(added=n)

if __name__ == '__main__':
    with app.app_context(): db().executescript(SCHEMA); seed()
    app.run(port=5000)
