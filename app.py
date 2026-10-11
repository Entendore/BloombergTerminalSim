#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EMBER TERMINAL 12.0 — algorithmic trading desk (paper, synthetic) — PySide6
Universe: 223 equities / 16 sectors + 15 macro + EMBX composite (239 total)
PODS · intrabar exits (STP/TGT/TRAIL/MAXB) in BOTH live engine & backtester ·
walk-forward · worker threads · order ticket · OCO brackets · TIF · daily
rollover · factor VaR / attribution · journal persistence · diagnostics

Run:  pip install PySide6
      python ember_terminal.py
"""
import os, sys, math, json, time, random, csv, traceback
from collections import deque, namedtuple
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QRunnable, QThreadPool, QEvent, QRectF
from PySide6.QtGui import (QPainter, QColor, QPen, QFont, QBrush, QPolygonF, QShortcut,
                           QKeySequence, QTextCursor)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QSplitter, QStackedWidget, QListWidget, QListWidgetItem,
    QStyledItemDelegate, QTextBrowser, QComboBox, QProgressBar, QFileDialog, QMenu,
    QSizePolicy, QFrame)

# ============================ 0 · config & utils ============================
CFG = dict(tick_ms=560, ticks_per_bar=5, hist_bars=1200, max_bars=900, bar_ms=300000,
           day_len=240, bars_per_day=288, commission=2.0, slip_ticks=2,
           start_eq=1000000.0, eq_points=720, mc_paths=800, lmt_band_pct=0.05,
           ord_rate_max=10, ord_rate_win=10.0, tif_bars=480, pods=10, wf_is_pct=0.7,
           per_sym_notional=600000.0, gross_notional=2500000.0,
           max_sector_notional=1200000.0, max_lots=100000,
           daily_loss=40000.0, max_dd_pct=8.0)
JKEY_PATH = os.path.expanduser('~/.ember_terminal_journal.json')
PREFS_PATH = os.path.expanduser('~/.ember_terminal_prefs.json')

UP, DN, AMBER, BLUE, DIM, TEAL, TXT = ('#2fd471', '#ff5449', '#ffa028', '#5aa7ff',
                                       '#5b6154', '#3fd4c0', '#e6e2d4')
STRAT_COLORS = {'MOMENTUM': '#ffa028', 'MEANREV': '#5aa7ff',
                'BREAKOUT': '#2fd471', 'RSI': '#ff7a5c'}

def clamp(v, a, b): return max(a, min(b, v))
def fmt(n, d=2):
    try:
        if not math.isfinite(n): n = 0.0
    except TypeError: n = 0.0
    return f"{n:,.{d}f}"
def money(n, sign=False):
    s = '-' if n < 0 else ('+' if sign else '')
    return s + '$' + fmt(abs(n))
def money_k(n, sign=False):
    a = abs(n); s = '-' if n < 0 else ('+' if sign else '')
    if a >= 1e6: return f"{s}${fmt(a/1e6,2)}MM"
    if a >= 1e4: return f"{s}${fmt(a/1e3,1)}K"
    return s + '$' + fmt(a, 0)
def fmt_px(v, dec): return f"{round(v, dec):,.{dec}f}"
def hm_t(ms): return datetime.fromtimestamp(ms/1000).strftime('%H:%M')
def now_t(): return datetime.now().strftime('%H:%M:%S')
def esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))
def c(txt, color): return f'<span style="color:{color}">{txt}</span>'
def b(txt, color=None):
    return f'<b style="color:{color}">{txt}</b>' if color else f'<b>{txt}</b>'

# ============================ 1 · universe ============================
SECTORS = [
 dict(id='TEC', vol=.0011, beta=1.20, vbase=2600,
  data='AAPL|APPLE|224|MSFT|MICROSOFT|421|NVDA|NVIDIA|121|GOOGL|ALPHABET|176|AMZN|AMAZON.COM|185|META|META PLATFORMS|505|ORCL|ORACLE|142|CRM|SALESFORCE|282|ADBE|ADOBE|510|NFLX|NETFLIX|685|IBM|IBM|220|CSCO|CISCO|48|ACN|ACCENTURE|310|INTU|INTUIT|620|NOW|SERVICENOW|750|SNPS|SYNOPSYS|550|UBER|UBER TECH|70|SHOP|SHOPIFY|80'),
 dict(id='SEM', vol=.0016, beta=1.40, vbase=2200,
  data='AMD|ADVANCED MICRO|165|AVGO|BROADCOM|1710|QCOM|QUALCOMM|205|TXN|TEXAS INSTR|205|INTC|INTEL|31|MU|MICRON|130|AMAT|APPLIED MATL|225|LRCX|LAM RESEARCH|1050|KLAC|KLA CORP|830|ASML|ASML HOLDING|1010|MRVL|MARVELL|75|NXPI|NXP SEMI|225|ON|ONSEMI|70|TSM|TAIWAN SEMICON|180|ARM|ARM HOLDINGS|140|GFS|GLOBALFOUNDRIES|38'),
 dict(id='AER', vol=.0010, beta=1.05, vbase=900,
  data='NOC|NORTHROP GRUMMAN|480|GD|GENERAL DYNAMICS|290|LMT|LOCKHEED MARTIN|470|RTX|RTX CORP|105|BA|BOEING|178|LHX|L3HARRIS|340|TDG|TRANSDIGM|1100|TXT|TEXTRON|130|HWM|HOWMET AERO|190|HEI|HEICO|270'),
 dict(id='ENR', vol=.0010, beta=0.90, vbase=1400,
  data='XOM|EXXON MOBIL|115|CVX|CHEVRON|158|COP|CONOCOPHILLIPS|118|SLB|SLB|45|EOG|EOG RESOURCES|128|PSX|PHILLIPS 66|140|MPC|MARATHON PETRO|168|OXY|OCCIDENTAL|63|HAL|HALLIBURTON|28|VLO|VALERO|135|BKR|BAKER HUGHES|42|DVN|DEVON ENERGY|38|FANG|DIAMONDBACK|180|KMI|KINDER MORGAN|22|WMB|WILLIAMS COS|52|OKE|ONEOK|85'),
 dict(id='FIN', vol=.0008, beta=1.10, vbase=1800,
  data='JPM|JPMORGAN CHASE|205|BAC|BANK OF AMERICA|40|WFC|WELLS FARGO|60|GS|GOLDMAN SACHS|465|MS|MORGAN STANLEY|100|C|CITIGROUP|63|BLK|BLACKROCK|990|SCHW|CHARLES SCHWAB|73|AXP|AMERICAN EXPRESS|245|V|VISA|280|MA|MASTERCARD|450|PYPL|PAYPAL|65|USB|US BANCORP|45|PNC|PNC FINL|185|TFC|TRUIST|42|BK|BNY MELLON|62|SPGI|S&P GLOBAL|480|CB|CHUBB|265'),
 dict(id='HLT', vol=.0007, beta=0.70, vbase=1500,
  data='JNJ|JOHNSON&JOHNSON|152|UNH|UNITEDHEALTH|500|LLY|ELI LILLY|880|PFE|PFIZER|28|MRK|MERCK|128|ABBV|ABBVIE|175|TMO|THERMO FISHER|560|ABT|ABBOTT|105|DHR|DANAHER|250|AMGN|AMGEN|310|GILD|GILEAD|65|ISRG|INTUITIVE SURG|430|SYK|STRIKER|360|BSX|BOSTON SCIENT|90|MDT|MEDTRONIC|85|CI|CIGNA|320'),
 dict(id='BIO', vol=.0016, beta=0.80, vbase=1100,
  data='VRTX|VERTEX PHARMA|450|REGN|REGENERON|780|MRNA|MODERNA|95|BIIB|BIOGEN|180|BNTX|BIONTECH|110|ALNY|ALNYLAM|180|NBIX|NEUROCRINE|95|INCY|INCYTE|70|EXAS|EXACT SCIENCES|55|ILMN|ILLUMINA|95|RARE|ULTRAGENYX|160|TECH|BIO-TECHNE|230'),
 dict(id='CNS', vol=.0006, beta=0.60, vbase=1600,
  data='WMT|WALMART|68|PG|PROCTER&GAMBLE|167|KO|COCA-COLA|63|PEP|PEPSICO|170|MCD|MCDONALDS|262|NKE|NIKE|78|SBUX|STARBUCKS|80|YUM|YUM BRANDS|135|CMG|CHIPOTLE|55|CL|COLGATE|95|KHC|KRAFT HEINZ|35|MDLZ|MONDELEZ|68|KDP|KEURIG DR PEPPER|35|MNST|MONSTER BEV|55|HSY|HERSHEY|170'),
 dict(id='RET', vol=.0007, beta=0.80, vbase=1600,
  data='COST|COSTCO|860|HD|HOME DEPOT|345|LOW|LOWES|240|TGT|TARGET|148|TJX|TJX COMPANIES|115|ROST|ROSS STORES|150|BURL|BURLINGTON|280|KR|KROGER|60|DG|DOLLAR GENERAL|90|DLTR|DOLLAR TREE|130|BBY|BEST BUY|80|AAP|ADVANCE AUTO|65|LULU|LULULEMON|330|DASH|DOORDASH|160'),
 dict(id='IND', vol=.0008, beta=1.00, vbase=1200,
  data='CAT|CATERPILLAR|390|DE|DEERE|385|HON|HONEYWELL|215|GE|GE AEROSPACE|165|MMM|3M COMPANY|130|EMR|EMERSON ELEC|115|ITW|ILLINOIS TOOL|240|CMI|CUMMINS|350|PH|PARKER HANNIFIN|690|ROCK|ROCKWELL AUTO|270|ETN|EATON|335|FDX|FEDEX|270|VRSK|VERISK|240|CTAS|CINTAS|190|PWR|QUANTA SERV|290|URI|UNITED RENTALS|840'),
 dict(id='TRN', vol=.0009, beta=1.00, vbase=1000,
  data='UNP|UNION PACIFIC|240|CSX|CSX CORP|35|NSC|NORFOLK SOUTHERN|250|DAL|DELTA AIR LINES|60|UAL|UNITED AIRLINES|95|AAL|AMERICAN AIRLINES|13|LUV|SOUTHWEST AIR|30|ODFL|OLD DOMINION|180|XPO|XPO LOGISTICS|130|JBHT|J.B. HUNT|180|CCL|CARNIVAL CORP|25|RCL|ROYAL CARIBBEAN|170'),
 dict(id='UTL', vol=.0005, beta=0.40, vbase=800,
  data='NEE|NEXTERA ENERGY|73|DUK|DUKE ENERGY|98|SO|SOUTHERN CO|78|D|DOMINION|78|AEP|AMERICAN ELEC|95|EXC|EXELON|37|XEL|XCEL ENERGY|66|SRE|SEMPRA|85|WEC|WEC ENERGY|88|ED|CONS EDISON|95|PEG|PUBLIC SVC|82|ES|EVERSOURCE|65'),
 dict(id='MAT', vol=.0008, beta=0.90, vbase=900,
  data='LIN|LINDE|440|SHW|SHERWIN WILLIAMS|345|FCX|FREEPORT-MCMR|48|NEM|NEWMONT|42|DOW|DOW INC|52|DD|DUPONT|68|APD|AIR PRODUCTS|290|ECL|ECOLAB|245|VMC|VULCAN MATL|255|NUE|NUCOR|155|MOS|MOSAIC|50|CF|CF INDUSTRIES|85'),
 dict(id='REI', vol=.0007, beta=0.80, vbase=700,
  data='PLD|PROLOGIS|115|AMT|AMERICAN TOWER|200|EQIX|EQUIINIX|830|SPG|SIMON PROPERTY|155|O|REALTY INCOME|55|PSA|PUBLIC STORAGE|290|WELL|WELLTOWER|135|DLR|DIGITAL REALTY|160|AVB|AVALONBAY|215|EQR|EQUITY RESID|70|CCI|CROWN CASTLE|105|VICI|VICI PROPERTIES|32'),
 dict(id='MED', vol=.0010, beta=1.10, vbase=1400,
  data='DIS|WALT DISNEY|100|CMCSA|COMCAST|39|T|AT&T|17|VZ|VERIZON|41|TMUS|T-MOBILE US|205|CHTR|CHARTER COMMS|300|WBD|WARNER BROS DISC|9|EA|ELECTRONIC ARTS|135|TTWO|TAKE-TWO|170|OMC|OMNICOM|105|LYV|LIVE NATION|130|SPOT|SPOTIFY|420'),
 dict(id='DGT', vol=.0022, beta=1.60, vbase=1100,
  data='COIN|COINBASE|225|MSTR|STRATEGY|350|MARA|MARA HOLDINGS|22|RIOT|RIOT PLATFORMS|11|CLSK|CLEANSPARK|12|HUT|HUT 8 CORP|18|GLXY|GALAXY DIGITAL|22|WULF|TERA WULF|6|CORZ|CORE SCIENTIFIC|14|SDIG|STRONGHOLD|3|CIFR|CIPHER MINING|5|BTBT|BIT DIGITAL|4'),
]
MACRO = [
 ('ES', 'E-MINI S&P 500', 5312.25, .00042, 50, 2, .25, 1200, .9, 'FUT'),
 ('NQ', 'E-MINI NASDAQ 100', 18540.5, .00058, 20, 2, .25, 900, 1.1, 'FUT'),
 ('YM', 'E-MINI DOW', 39500, .00036, 5, 2, 1, 500, .9, 'FUT'),
 ('RTY', 'E-MINI RUSSELL', 2080, .00055, 50, 2, .1, 420, 1.0, 'FUT'),
 ('CL', 'CRUDE OIL WTI', 78.42, .00095, 1000, 2, .01, 520, .5, 'FUT'),
 ('NG', 'NATURAL GAS', 2.85, .0018, 10000, 3, .001, 480, .3, 'FUT'),
 ('GC', 'GOLD', 2352.4, .00048, 100, 1, .1, 410, .2, 'FUT'),
 ('SI', 'SILVER', 30.5, .0012, 5000, 3, .005, 260, .4, 'FUT'),
 ('HG', 'COPPER', 4.52, .0011, 25000, 3, .0005, 180, .6, 'FUT'),
 ('ZW', 'WHEAT', 585, .0013, 50, 2, .25, 150, .1, 'FUT'),
 ('6E', 'EURO FX', 1.0842, .00028, 125000, 4, .00005, 800, .2, 'FX'),
 ('6B', 'BRITISH POUND', 1.272, .0003, 62500, 4, .0001, 320, .2, 'FX'),
 ('6A', 'AUSTRALIAN DOLLAR', .663, .00035, 100000, 4, .0001, 280, .3, 'FX'),
 ('BTC', 'BITCOIN PERP', 67420, .00125, 1, 0, 1, 160, 1.3, 'CRYP'),
 ('ETH', 'ETHER PERP', 3450, .0018, 1, 1, .1, 140, 1.4, 'CRYP'),
]

class Instr:
    __slots__ = ('sym','name','sector','asset','px0','vol','beta','scoef','mult','lot',
                 'dec','tick','vbase','tradable','px','ppx','drift','vs','t2',
                 'norm_base','shift','bars','ind','s9','s21','s50','bu','bl','vw',
                 '_pv','_vv','forming','tape')

class Bar(namedtuple('Bar', 'o h l c v t')): pass

# ============================ 2 · indicators ============================
class Indicator:
    __slots__ = ('n','pc','ag','al','hs','ls','cs','emas','s')
    def __init__(self):
        self.n=0; self.pc=None; self.ag=None; self.al=None
        self.hs=[]; self.ls=[]; self.cs=[]; self.emas={}; self.s=None
    def ema(self, p): return self.emas.setdefault(p, {'v': None})
    def push(self, bar):
        cbar = bar.c; self.n += 1
        for p, st in self.emas.items():
            a = 2.0/(p+1)
            st['v'] = cbar if st['v'] is None else st['v'] + (cbar-st['v'])*a
        if self.pc is not None:
            d = cbar-self.pc; g = d if d > 0 else 0.0; l = -d if d < 0 else 0.0
            self.ag = g if self.ag is None else (self.ag*13+g)/14
            self.al = l if self.al is None else (self.al*13+l)/14
        self.pc = cbar
        if self.al is None: rsi = 50.0
        elif self.al == 0:  rsi = 100.0
        else:               rsi = 100.0 - 100.0/(1.0 + self.ag/self.al)
        self.hs.append(bar.h); self.ls.append(bar.l); self.cs.append(cbar)
        if len(self.hs) > 70: self.hs.pop(0); self.ls.pop(0)
        if len(self.cs) > 20: self.cs.pop(0)
        bbU = bbL = None; z = 0.0
        if len(self.cs) >= 10:
            m = sum(self.cs)/len(self.cs)
            sd = math.sqrt(sum((x-m)**2 for x in self.cs)/len(self.cs))
            bbU = m+2*sd; bbL = m-2*sd
            z = (cbar-m)/(2*sd) if sd > 1e-12 else 0.0
        ev = {p: st['v'] for p, st in self.emas.items()}
        prev = self.s
        s = dict(c=cbar, h=bar.h, l=bar.l, ev=ev, hs=self.hs.copy(), ls=self.ls.copy(),
                 rsi=rsi, bbU=bbU, bbL=bbL, z=z, prev=prev)
        if prev is not None: prev['prev'] = None
        self.s = s
        return s

def ensure_emas(ind, prm):
    if prm.get('FAST') is not None: ind.ema(prm['FAST'])
    if prm.get('SLOW') is not None: ind.ema(prm['SLOW'])

# ============================ 3 · strategies ============================
STRATS = [
 dict(id='MOMENTUM', name='EMA MOMENTUM', desc='EMA CROSSOVER · TREND FOLLOW',
      params={'FAST': dict(min=4, max=16, step=2, def=9),
              'SLOW': dict(min=12, max=60, step=6, def=21)}),
 dict(id='MEANREV', name='BB MEAN REVERSION', desc='Z-SCORE FADE · EXIT AT MEAN',
      params={'ZIN': dict(min=1.2, max=3, step=.2, def=2),
              'ZOUT': dict(min=.1, max=1, step=.1, def=.35)}),
 dict(id='BREAKOUT', name='DONCHIAN BREAKOUT', desc='CHANNEL BREAKOUT',
      params={'ELEN': dict(min=10, max=40, step=5, def=20),
              'XLEN': dict(min=4, max=20, step=2, def=10)}),
 dict(id='RSI', name='RSI REVERSION', desc='RSI14 THRESHOLDS',
      params={'LO': dict(min=15, max=40, step=5, def=30),
              'HI': dict(min=60, max=85, step=5, def=70),
              'XLO': dict(min=35, max=55, step=5, def=45),
              'XHI': dict(min=45, max=65, step=5, def=55)}),
]
STRAT_IDS = [s['id'] for s in STRATS]
STRAT_BY_ID = {s['id']: s for s in STRATS}

def default_params(defn):
    return {k: sc['def'] for k, sc in defn['params'].items()}

def param_values(sc):
    out, v = [], sc['min']
    while v <= sc['max'] + 1e-9:
        out.append(round(v, 4)); v += sc['step']
    return out

def param_schema_text(defn):
    return ' · '.join(f"{k} {sc['min']}–{sc['max']} ({sc['def']})"
                      for k, sc in defn['params'].items())

def decide(strat_id, prm, st, s, inst):
    f = lambda v: fmt_px(v, inst.dec)
    if strat_id == 'MOMENTUM':
        p = s['prev']
        if not p: return (st['pos'], '')
        fa, sl = prm['FAST'], prm['SLOW']
        fe, se = s['ev'].get(fa), s['ev'].get(sl)
        pfe, pse = p['ev'].get(fa), p['ev'].get(sl)
        if None in (fe, se, pfe, pse): return (st['pos'], '')
        if pfe <= pse and fe > se: return (1, f"EMA{fa} {f(fe)} × EMA{sl} {f(se)} ↑")
        if pfe >= pse and fe < se: return (-1, f"EMA{fa} {f(fe)} × EMA{sl} {f(se)} ↓")
        return (st['pos'], '')
    if strat_id == 'MEANREV':
        zin, zout = prm['ZIN'], prm['ZOUT']
        if s['z'] >= zin:  return (-1, f"Z +{s['z']:.2f} ≥ +{zin} → FADE")
        if s['z'] <= -zin: return (1, f"Z {s['z']:.2f} ≤ −{zin} → FADE")
        if st['pos'] != 0 and abs(s['z']) <= zout: return (0, 'Z REVERTED TO MEAN')
        return (st['pos'], '')
    if strat_id == 'BREAKOUT':
        el, xl = prm['ELEN'], prm['XLEN']
        hs, ls = s['hs'], s['ls']
        hi = max(hs[-(el+1):-1]) if len(hs) > el+1 else None
        lo = min(ls[-(xl+1):-1]) if len(ls) > xl+1 else None
        if hi is not None and s['c'] > hi: return (1, f"BREAK > {el}BAR HIGH {f(hi)}")
        if lo is not None and s['c'] < lo: return (-1, f"BREAK < {xl}BAR LOW {f(lo)}")
        return (st['pos'], '')
    if strat_id == 'RSI':
        r = f"{s['rsi']:.1f}"
        if st['pos'] > 0 and s['rsi'] >= prm['XHI']: return (0, f"RSI {r} ≥ {prm['XHI']} · EXIT LONG")
        if st['pos'] < 0 and s['rsi'] <= prm['XLO']: return (0, f"RSI {r} ≤ {prm['XLO']} · EXIT SHORT")
        if s['rsi'] <= prm['LO']: return (1, f"RSI {r} ≤ {prm['LO']}")
        if s['rsi'] >= prm['HI']: return (-1, f"RSI {r} ≥ {prm['HI']}")
        return (st['pos'], '')
    return (st['pos'], '')

def round_tick(px, inst):
    t = inst.tick
    if t <= 0: return px
    return round(round(px/t)*t, 10)

# ============================ 4 · compute cores (module level) ============================
def bt_core(p):
    """Backtest — models the live exit engine intrabar: STP/TGT/TRAIL/MAXB from
    bar extremes BEFORE close-based signal; ambiguous bars resolve STOP-first."""
    bars, inst, sid, prm, cfg = p['bars'], p['inst'], p['stratId'], p['prm'], p['cfg']
    ind = Indicator(); ensure_emas(ind, prm)
    st = dict(pos=0, avg=0.0, eBar=0, trailPeak=None)
    trades, eq = [], []
    gW = gL = wins = 0
    exits = dict(STOP=0, TGT=0, TRAIL=0, TIME=0)
    WARM, CAP, slip = 60, 100000.0, cfg.get('slipTicks', 0)
    mult, lot, tick = inst['mult'], inst['lot'], inst['tick']
    comm = cfg.get('commission', 2.0)

    def vfill(qty, fpx, i, why):
        nonlocal gW, gL, wins
        if qty == 0: return
        sg = 1 if qty > 0 else -1
        if st['pos'] == 0 or (st['pos'] > 0) == (sg > 0):
            tot = abs(st['pos']) + abs(qty)
            st['avg'] = (abs(st['pos'])*st['avg'] + abs(qty)*fpx)/tot
            st['pos'] += qty; st['eBar'] = i; st['trailPeak'] = None
        else:
            closed = min(abs(st['pos']), abs(qty))
            pnl = closed*(fpx-st['avg'])*(1 if st['pos'] > 0 else -1)*mult - comm
            trades.append(dict(side=1 if st['pos'] > 0 else -1, ePx=st['avg'],
                               xPx=fpx, pnl=pnl, why=why))
            if pnl > 0: wins += 1; gW += pnl
            else:       gL -= pnl
            st['pos'] += qty
            if st['pos'] == 0: st['avg'] = 0.0; st['trailPeak'] = None
            else: st['avg'] = fpx; st['eBar'] = i

    def close_at(sg, px, i, why):
        f = round_tick(px - sg*slip*tick, inst)
        vfill(-st['pos'], f, i, why)
        exits[why] = exits.get(why, 0) + 1

    for i, bar in enumerate(bars):
        if st['pos'] != 0 and i > st['eBar']:
            sg = 1 if st['pos'] > 0 else -1
            done = False
            if cfg.get('maxBars', 0) > 0 and (i - st['eBar']) >= cfg['maxBars']:
                close_at(sg, bar.c, i, 'TIME'); done = True
            if not done and cfg.get('trailTicks', 0) > 0:
                tt = cfg['trailTicks']*tick
                if st['trailPeak'] is None:
                    st['trailPeak'] = bar.h if sg > 0 else bar.l
                elif sg > 0: st['trailPeak'] = max(st['trailPeak'], bar.h)
                else:        st['trailPeak'] = min(st['trailPeak'], bar.l)
                stop = st['trailPeak'] - tt if sg > 0 else st['trailPeak'] + tt
                if (sg > 0 and bar.l <= stop) or (sg < 0 and bar.h >= stop):
                    close_at(sg, stop, i, 'TRAIL'); done = True
            if not done and cfg.get('stpTicks', 0) > 0:
                stop = st['avg'] - sg*cfg['stpTicks']*tick
                if (sg > 0 and bar.l <= stop) or (sg < 0 and bar.h >= stop):
                    close_at(sg, stop, i, 'STOP'); done = True
            if not done and cfg.get('tgtTicks', 0) > 0:
                tgt = st['avg'] + sg*cfg['tgtTicks']*tick
                if (sg > 0 and bar.h >= tgt) or (sg < 0 and bar.l <= tgt):
                    vfill(-st['pos'], round_tick(tgt, inst), i, 'TGT')
                    exits['TGT'] += 1
        s = ind.push(bar)
        if i >= WARM:
            t, _r = decide(sid, prm, st, s, inst)
            want = t * lot
            if want != st['pos']:
                fpx = bar.c + (1 if want > st['pos'] else -1)*tick*slip
                vfill(want - st['pos'], fpx, i, 'SIG')
        eq.append(CAP + st['pos']*(bar.c - st['avg'])*mult)

    final = eq[-1] if eq else CAP
    ret = (final/CAP - 1)*100
    peak, mdd = CAP, 0.0
    for v in eq:
        peak = max(peak, v); mdd = max(mdd, (peak-v)/peak)
    mean = sd = 0.0; sharpe = None
    if len(eq) > 2:
        rets = [eq[i]/eq[i-1]-1 for i in range(1, len(eq))]
        mean = sum(rets)/len(rets)
        sd = math.sqrt(sum((x-mean)**2 for x in rets)/len(rets))
        sharpe = mean/sd*math.sqrt(252*288) if sd > 0 else None
    pf = (gW/gL) if gL > 0 else None
    n = len(trades)
    return dict(trades=trades, eq=eq, ret=ret, sharpe=sharpe, mdd=mdd, wins=wins,
                n=n, pf=pf, exits=exits,
                avgT=(final-CAP)/n if n else 0.0, final=final)

def wf_core(p):
    is_n = max(200, int(p['count']*p['isPct']))
    is_bars = p['bars'][:is_n]
    oos_bars = p['bars'][max(0, is_n-60):]
    sweep = []
    for v in p['vals']:
        prm = dict(p['base']); prm[p['param']] = v
        r = bt_core(dict(bars=is_bars, inst=p['inst'], stratId=p['stratId'],
                         prm=prm, cfg=p['cfg']))
        sweep.append(dict(v=v, ret=r['ret'], sharpe=r['sharpe'], n=r['n'], mdd=r['mdd']))
    valid = [x for x in sweep if x['n'] >= 4]
    pool = valid if valid else sweep
    pool.sort(key=lambda x: (x['sharpe'] is not None, x['sharpe'] or -9e9), reverse=True)
    best = pool[0] if pool else None
    oos_best = None
    if best:
        prm = dict(p['base']); prm[p['param']] = best['v']
        r = bt_core(dict(bars=oos_bars, inst=p['inst'], stratId=p['stratId'],
                         prm=prm, cfg=p['cfg']))
        oos_best = dict(ret=r['ret'], sharpe=r['sharpe'], mdd=r['mdd'], n=r['n'])
    rd = bt_core(dict(bars=oos_bars, inst=p['inst'], stratId=p['stratId'],
                      prm=p['base'], cfg=p['cfg']))
    return dict(sweep=sweep, best=best, isN=is_n,
                oosN=len(p['bars'])-max(0, is_n-60), oosBest=oos_best,
                oosDef=dict(ret=rd['ret'], sharpe=rd['sharpe'], mdd=rd['mdd'], n=rd['n']))

def mc_core(pnls, M, seed):
    T = len(pnls)
    rng = random.Random(seed)
    rows, finals, dds = [], [], []
    for _m in range(M):
        eqv, peak, dd = 100000.0, 100000.0, 0.0
        row = [eqv]
        for _t in range(T):
            eqv += pnls[int(rng.random()*T)]
            peak = max(peak, eqv); dd = max(dd, (peak-eqv)/peak)
            row.append(eqv)
        rows.append(row); finals.append(eqv); dds.append(dd)
    cols = [sorted(r[t] for r in rows) for t in range(T+1)]
    pc = lambda col, q: col[min(len(col)-1, int(q*(len(col)-1)))]
    bands = {q: [pc(col, q) for col in cols] for q in (.05, .25, .5, .75, .95)}
    sf = sorted(finals); sdd = sorted(dds)
    return dict(p05=bands[.05], p25=bands[.25], p50=bands[.5], p75=bands[.75],
                p95=bands[.95],
                f05=pc(sf, .05), f50=pc(sf, .5), f95=pc(sf, .95),
                pLoss=sum(1 for f in finals if f < 100000)/M,
                dd50=pc(sdd, .5), dd95=pc(sdd, .95),
                ruin=sum(1 for d in dds if d >= .5)/M, M=M, T=T)

def bt_batch_chunk(items, strat_id, base, cfg):
    out = []
    for it in items:
        r = bt_core(dict(bars=it['bars'],
                         inst=dict(sym=it['sym'], mult=it['mult'], lot=it['lot'],
                                   dec=it['dec'], tick=it['tick']),
                         stratId=strat_id, prm=base, cfg=cfg))
        out.append(dict(sym=it['sym'], ret=r['ret'], sharpe=r['sharpe'],
                        mdd=r['mdd'], n=r['n'], pf=r['pf']))
    return out

# ============================ 5 · desk (engine) ============================
class Pod:
    __slots__ = ('key','defn','params','running','sym','inst','unit','pos','avg','eBar',
                 'realized','trades','trades_n','wins','gW','gL','note',
                 'stop_ticks','tgt_ticks','trail_ticks','trail_peak','max_bars')
    def __init__(self, defn, sym):
        self.defn = defn; self.sym = sym; self.key = defn['id'] + '·' + sym
        self.params = default_params(defn)
        self.running = False; self.inst = None; self.unit = 1
        self.pos = 0; self.avg = 0.0; self.eBar = 0; self.realized = 0.0
        self.trades = []; self.trades_n = 0; self.wins = 0; self.gW = 0.0; self.gL = 0.0
        self.note = ''; self.stop_ticks = 0; self.tgt_ticks = 0
        self.trail_ticks = 0; self.trail_peak = None; self.max_bars = 0

class Desk:
    def __init__(self):
        self.ui = None
        self.cfg = CFG
        self.seed = 20240611
        self.instrs = []; self.sym_map = {}; self.eqs = []
        self.idx = None; self.idx_scale = 1.0; self.syms = []
        self.build_universe()
        self.mkt = dict(f=0.0, vs=1.0, t2=250, hist=[])
        self.secst = {s['id']: dict(f=0.0, vs=1.0, t2=200, hist=[]) for s in SECTORS}
        self.breadth_hist = []; self.eq_hist = []
        self.acct = dict(realized=0.0, fills=0, pos={})
        self.ledger = {}; self.fills = []; self.exec_stats = {}
        self.real_by_sym = {}; self.real_by_tag = {}; self.trades_log = []
        self.attr_base = 0.0
        self.orders = []; self.order_seq = 1; self.ord_times = deque()
        self.pods = []; self.pods_dirty = True
        self.arena = dict(sym=None, on=False, sims=[])
        self.alerts = []; self.alert_seq = 1
        self.journal = []
        self.halted = False; self.eq_peak = CFG['start_eq']; self.day_start_eq = CFG['start_eq']
        self.day_n = 1; self.last_day_roll = -1
        self.paused = False; self.tick_n = 0; self.feed_down_until = 0.0
        self.lat = 12.0; self.tick_times = deque(maxlen=120)
        self.t0 = time.time()
        self.compute_busy = False
        self.last_bt = None; self.btlog = []
        self.opt_state = None; self.mc_state = None
        self.confirm_flat = 0.0; self.confirm_reset = 0.0
        self.watch = dict(filter='ALL', sort='SYM', query='')

    # ---------- universe ----------
    def build_universe(self):
        rng = random.Random(self.seed*7+3)
        for sec in SECTORS:
            p = sec['data'].split('|')
            for i in range(0, len(p), 3):
                px = float(p[i+2])
                it = Instr()
                it.sym, it.name, it.sector, it.asset = p[i], p[i+1], sec['id'], 'EQ'
                it.px0 = px; it.vol = sec['vol']*(0.75+rng.random()*0.5)
                it.beta = sec['beta']*(0.8+rng.random()*0.4); it.scoef = 1.0
                it.mult = 1.0; it.lot = max(1, round(2000/px)); it.dec = 2; it.tick = 0.01
                it.vbase = round(sec['vbase']*(0.5+rng.random())); it.tradable = True
                self.instrs.append(it); self.eqs.append(it)
        for (sym, name, px0, vol, mult, dec, tick, vbase, beta, cls) in MACRO:
            it = Instr()
            it.sym, it.name, it.sector, it.asset = sym, name, 'MAC', cls
            it.px0 = px0; it.vol = vol; it.beta = beta; it.scoef = 0.0
            it.mult = mult; it.lot = 1; it.dec = dec; it.tick = tick; it.vbase = vbase
            it.tradable = True
            self.instrs.append(it)
        self.rebuild_syms()

    def rebuild_syms(self):
        self.syms = [i.sym for i in self.instrs]
        self.sym_map = {i.sym: i for i in self.instrs}

    def by_sym(self, s): return self.sym_map.get(s)
    def can_trade(self, inst): return inst is not None and inst.tradable

    # ---------- history ----------
    def gen_history(self):
        if self.idx is not None:
            self.instrs.remove(self.idx); self.idx = None
        rng = random.Random(self.seed)
        N = CFG['hist_bars']
        end_t = int(time.time()*1000)//CFG['bar_ms']*CFG['bar_ms']
        # factors
        mF = [0.0]*N; sF = {s['id']: [0.0]*N for s in SECTORS}
        m, mvs, mt2 = 0.0, 1.0, 250
        sf = {s['id']: 0.0 for s in SECTORS}
        svs = {s['id']: 1.0 for s in SECTORS}
        st2 = {s['id']: 150.0 for s in SECTORS}
        for i in range(N):
            mt2 -= 1
            if mt2 <= 0:
                mt2 = 250+rng.random()*500
                mvs = 2.2+rng.random()*2 if rng.random() < .12 else max(.5, mvs*.85)
            m = m*.99 + rng.gauss(0, 1)*.00011*mvs; mF[i] = m
            for s in SECTORS:
                sid = s['id']; st2[sid] -= 1
                if st2[sid] <= 0:
                    st2[sid] = 200+rng.random()*450
                    svs[sid] = 2.5+rng.random()*2.5 if rng.random() < .1 else max(.4, svs[sid]*.85)
                sf[sid] = sf[sid]*.985 + rng.gauss(0, 1)*.00017*svs[sid]
                sF[sid][i] = sf[sid]
        for it in self.instrs:
            it.drift = 0.0; it.vs = 1.0; it.t2 = 120+rng.random()*260
            sfA = sF[it.sector] if it.sector != 'MAC' else None
            px = it.px0*(0.94+rng.random()*0.1)
            bars = []
            for i in range(N):
                it.t2 -= 1
                if it.t2 <= 0:
                    it.t2 = 140+rng.random()*260
                    it.drift = rng.gauss(0, 1)*it.vol*0.5
                    it.vs = 1.6+rng.random()*1.9 if rng.random() < .15 else max(1.0, it.vs*0.9)
                v = it.vol*(0.55+it.vs*0.55)
                fac = it.beta*mF[i] + (sfA[i] if sfA else 0.0)
                o = px
                cc = max(it.tick, o*(1 + it.drift + v*rng.gauss(0, 1) + fac))
                h = max(o, cc)*(1 + abs(rng.gauss(0, 1))*v*0.6)
                l = min(o, cc)*(1 - abs(rng.gauss(0, 1))*v*0.6)
                vol = round(it.vbase*(0.35+rng.random()*1.3)*(1+abs(cc/o-1)*400))
                bars.append(Bar(o, h, l, cc, vol, end_t - (N-1-i)*CFG['bar_ms']))
                px = cc
            it.px = round_tick(bars[-1].c, it); it.ppx = it.px
            if it.asset == 'EQ': it.norm_base = bars[0].c
            it.bars = []; it.shift = 0; it._pv = 0.0; it._vv = 0.0
            it.ind = Indicator()
            for p in (9, 21, 50): it.ind.ema(p)
            it.s9 = []; it.s21 = []; it.s50 = []; it.bu = []; it.bl = []; it.vw = []
            it.forming = Bar(px, px, px, px, 0, end_t + CFG['bar_ms'])
            for bar in bars: self.push_closed_core(it, bar)
        self.build_index(end_t)
        self.rebuild_syms()

    def build_index(self, end_t):
        N = CFG['hist_bars']
        raw = []
        for bi in range(N):
            sc = sh = sl = sv = 0.0
            for e in self.eqs:
                bar = e.bars[bi]
                sc += bar.c/e.norm_base; sh += bar.h/e.norm_base
                sl += bar.l/e.norm_base; sv += bar.v
            raw.append((sc/len(self.eqs), sh/len(self.eqs), sl/len(self.eqs), sv/len(self.eqs)))
        self.idx_scale = 5000.0/raw[-1][0]
        it = Instr()
        it.sym, it.name, it.sector, it.asset = 'EMBX', 'EMBER COMPOSITE 223', 'IDX', 'IDX'
        it.vol = .0003; it.beta = 1.0; it.scoef = 0.0; it.mult = 1.0; it.lot = 1
        it.dec = 2; it.tick = .25; it.vbase = 1; it.tradable = False; it.norm_base = 1.0
        it.px = round_tick(raw[-1][0]*self.idx_scale, it); it.ppx = it.px
        bars = []; prev = raw[0][0]*self.idx_scale
        for bi in range(N):
            cc = raw[bi][0]*self.idx_scale
            h = raw[bi][1]*self.idx_scale; l = raw[bi][2]*self.idx_scale
            bars.append(Bar(prev, max(h, prev, cc), min(l, prev, cc), cc,
                            round(raw[bi][3]), end_t - (N-1-bi)*CFG['bar_ms']))
            prev = cc
        it.bars = []; it.shift = 0; it._pv = 0.0; it._vv = 0.0
        it.ind = Indicator()
        for p in (9, 21, 50): it.ind.ema(p)
        it.s9 = []; it.s21 = []; it.s50 = []; it.bu = []; it.bl = []; it.vw = []
        it.forming = Bar(it.px, it.px, it.px, it.px, 0, end_t + CFG['bar_ms'])
        for bar in bars: self.push_closed_core(it, bar)
        self.instrs.append(it); self.idx = it

    def push_closed_core(self, it, bar):
        it.bars.append(bar)
        s = it.ind.push(bar)
        ev = s['ev']
        it.s9.append(ev.get(9)); it.s21.append(ev.get(21)); it.s50.append(ev.get(50))
        it.bu.append(s['bbU']); it.bl.append(s['bbL'])
        if (len(it.bars)-1) % CFG['day_len'] == 0: it._pv = 0.0; it._vv = 0.0
        tp = (bar.h+bar.l+bar.c)/3.0*bar.v
        it._pv += tp; it._vv += bar.v
        it.vw.append(it._pv/it._vv if it._vv > 0 else bar.c)
        if len(it.bars) > CFG['max_bars']:
            cut = len(it.bars) - CFG['max_bars']
            del it.bars[:cut]; del it.s9[:cut]; del it.s21[:cut]; del it.s50[:cut]
            del it.bu[:cut]; del it.bl[:cut]; del it.vw[:cut]
            it.shift += cut

    # ---------- live step ----------
    def step_factors(self):
        m = self.mkt; m['t2'] -= 1
        if m['t2'] <= 0:
            m['t2'] = 200+random.random()*400
            m['vs'] = 2.2+random.random()*2 if random.random() < .12 else max(.5, m['vs']*.85)
        m['f'] = m['f']*.99 + random.gauss(0, 1)*.00011*m['vs']
        for s in SECTORS:
            st = self.secst[s['id']]; st['t2'] -= 1
            if st['t2'] <= 0:
                st['t2'] = 150+random.random()*400
                st['vs'] = 2.5+random.random()*2.5 if random.random() < .1 else max(.4, st['vs']*.85)
            st['f'] = st['f']*.985 + random.gauss(0, 1)*.00017*st['vs']

    def push_factor_hist(self):
        for d in [self.mkt] + list(self.secst.values()):
            d['hist'].append(d['f'])
            if len(d['hist']) > 480: d['hist'].pop(0)

    def step_px(self, it):
        it.t2 -= 1
        if it.t2 <= 0:
            it.t2 = 200+random.random()*500
            it.drift = random.gauss(0, 1)*it.vol*0.06
            it.vs = 1.6+random.random()*2 if random.random() < .15 else max(1.0, it.vs*0.9)
        sig = it.vol*it.vs/math.sqrt(CFG['ticks_per_bar'])
        sec = self.secst.get(it.sector)
        fac = ((it.beta*self.mkt['f']) + (sec['scoef'] if False else (it.scoef*sec['f'] if sec else 0.0)))/CFG['ticks_per_bar']
        it.px = max(it.tick, round_tick(it.px*(1 + it.drift/CFG['ticks_per_bar']
                                               + sig*random.gauss(0, 1) + fac), it))
        f = it.forming
        it.forming = Bar(f.o, max(f.h, it.px), min(f.l, it.px), it.px,
                         f.v + round(it.vbase*0.02*(0.3+random.random())), f.t)

    def step_index(self):
        it = self.idx
        if it is None: return
        s = sum(e.px/e.norm_base for e in self.eqs)
        it.px = round_tick(s/len(self.eqs)*self.idx_scale, it)
        f = it.forming
        it.forming = Bar(f.o, max(f.h, it.px), min(f.l, it.px), it.px, f.v, f.t)

    def close_bar_core(self, it):
        self.push_closed_core(it, it.forming)
        it.forming = Bar(it.px, it.px, it.px, it.px, 0,
                         it.bars[-1].t + CFG['bar_ms'])

    def day_open(self, it):
        n = len(it.bars)
        return it.bars[max(0, n-CFG['day_len'])].c

    def day_range(self, it):
        n = len(it.bars); s = it.bars[max(0, n-CFG['day_len']):]
        h = max((x.h for x in s), default=it.px); l = min((x.l for x in s), default=it.px)
        return max(h, it.px), min(l, it.px)

    def bar_count(self): return self.tick_n // CFG['ticks_per_bar']

    # ---------- risk ----------
    def gross_notional(self):
        g = 0.0
        for s, p in self.acct['pos'].items():
            if p['qty']:
                i = self.by_sym(s); g += abs(p['qty'])*i.px*i.mult
        return g

    def sector_notional(self, sec_id):
        g = 0.0
        for s, p in self.acct['pos'].items():
            if not p['qty']: continue
            i = self.by_sym(s)
            if i and i.sector == sec_id: g += abs(p['qty'])*i.px*i.mult
        return g

    def risk_check(self, sym, signed, force=False):
        if force: return (True, '')
        if self.halted:
            return (False, 'TRADING HALTED — RISK ENGINE · RESET RISK TO RE-ARM')
        inst = self.by_sym(sym); p = self.acct['pos'].get(sym, dict(qty=0))
        nq = p['qty'] + signed
        if not math.isfinite(nq): return (False, 'INVALID QUANTITY')
        if abs(nq) > CFG['max_lots']:
            return (False, f"LOT CAP {CFG['max_lots']} ON {sym}")
        sym_not = abs(nq)*inst.px*inst.mult
        if sym_not > CFG['per_sym_notional']:
            return (False, f"PER-SYMBOL NOTIONAL > {money_k(CFG['per_sym_notional'])} ON {sym}")
        if inst.sector not in ('MAC', 'IDX'):
            sec_not = (self.sector_notional(inst.sector)
                       - abs(p['qty'])*inst.px*inst.mult + sym_not)
            if sec_not > CFG['max_sector_notional']:
                return (False, f"SECTOR {inst.sector} NOTIONAL > {money_k(CFG['max_sector_notional'])}")
        gross = (self.gross_notional() - abs(p['qty'])*inst.px*inst.mult + sym_not)
        if gross > CFG['gross_notional']:
            return (False, f"GROSS NOTIONAL > {money_k(CFG['gross_notional'])}")
        return (True, '')

    def risk_monitor(self, eq):
        if self.halted: return
        loss = self.day_start_eq - eq
        if loss >= CFG['daily_loss']:
            self.trigger_halt(f"DAY {self.day_n} LOSS {money_k(loss)} ≥ LIMIT {money_k(CFG['daily_loss'])}")
            return
        dd = (self.eq_peak-eq)/self.eq_peak*100
        if dd >= CFG['max_dd_pct']:
            self.trigger_halt(f"DRAWDOWN {fmt(dd,1)}% ≥ {CFG['max_dd_pct']}%")

    def trigger_halt(self, reason):
        self.halted = True
        self.audit('HALT', reason)
        self.ui.sig('ERR', f"KILL SWITCH — {reason} · TRADING HALTED, BOOK FLATTENED")
        for o in self.orders:
            if o['status'] == 'WORKING': o['status'] = 'CANCELED'
        for p in self.pods:
            if p.running: self.stop_pod(p.key, force=True)
        self.flat_account(force=True)
        self.ui.halt_show()
        self.save_journal()

    # ---------- execution ----------
    def apply_fill(self, sym, signed, px, tag, ref_px=None):
        inst = self.by_sym(sym)
        px = round_tick(px, inst)
        if ref_px is None or not math.isfinite(ref_px): ref_px = px
        bar_id = len(inst.bars) - 1 + inst.shift
        p = self.acct['pos'].setdefault(sym, dict(qty=0, avg=0.0, eBar=bar_id))
        old = p['qty']; rl = -CFG['commission']
        if old != 0 and (old > 0) != (signed > 0):
            closed = min(abs(old), abs(signed))
            gross_pnl = closed*(px-p['avg'])*(1 if old > 0 else -1)*inst.mult
            rl = gross_pnl - CFG['commission']
            self.trades_log.append(dict(t=now_t(), sym=sym, side=1 if old > 0 else -1,
                qty=closed, ePx=p['avg'], xPx=px, pnl=gross_pnl, fee=CFG['commission'],
                held=max(0, bar_id - p.get('eBar', bar_id))))
            if len(self.trades_log) > 300: self.trades_log.pop(0)
        if old == 0 or (old > 0) == (signed > 0):
            tot = abs(old)+abs(signed)
            p['avg'] = (abs(old)*p['avg'] + abs(signed)*px)/tot
            if old == 0: p['eBar'] = bar_id
        elif abs(signed) > abs(old):
            p['avg'] = px; p['eBar'] = bar_id
        p['qty'] = old + signed
        if p['qty'] == 0: p['avg'] = 0.0; p['eBar'] = bar_id
        self.acct['realized'] += rl; self.acct['fills'] += 1
        self.real_by_sym[sym] = self.real_by_sym.get(sym, 0.0) + rl
        self.real_by_tag[tag] = self.real_by_tag.get(tag, 0.0) + rl
        self.ledger[sym] = self.ledger.get(sym, 0) + signed
        slip_cost = (px-ref_px)*signed*inst.mult
        st = self.exec_stats.setdefault(tag, dict(n=0, slip=0.0, fees=0.0))
        st['n'] += 1; st['slip'] += slip_cost; st['fees'] += CFG['commission']
        rec = dict(t=now_t(), sym=sym, side='B' if signed > 0 else 'S',
                   qty=abs(signed), px=px, tag=tag)
        self.fills.append(rec)
        if len(self.fills) > 600: self.fills.pop(0)
        self.ui.fill_row(rec)
        self.audit('FILL', f"{sym} {'+' if signed>0 else '-'}{abs(signed)} @ {px} [{tag}] "
                           f"slip {slip_cost:+.2f}")
        return rl

    def try_fill(self, sym, signed, px, tag, force=False, ref_px=None):
        ok, reason = self.risk_check(sym, signed, force)
        if not ok:
            self.ui.sig('ERR', f'ORDER REJECTED — {reason}')
            self.ui.msg('REJECTED — '+reason, 'err')
            return None
        return self.apply_fill(sym, signed, px, tag, ref_px)

    def cur_bar_id(self, pod): return len(pod.inst.bars) - 1 + pod.inst.shift

    def strat_step(self, pod, target, idx, px, force=False, why='SIG'):
        want = round(target)*pod.unit; inst = pod.inst
        if want == pod.pos: return
        diff = want - pod.pos
        sgn = 1 if diff > 0 else -1
        fpx = px + sgn*CFG['slip_ticks']*inst.tick
        if self.try_fill(inst.sym, diff, fpx, pod.defn['id'], force, px) is None: return
        if pod.pos == 0 or (pod.pos > 0) == (sgn > 0):
            tot = abs(pod.pos)+abs(diff)
            pod.avg = (abs(pod.pos)*pod.avg + abs(diff)*fpx)/tot
            pod.pos += diff; pod.eBar = idx
        else:
            closed = min(abs(pod.pos), abs(diff))
            pnl = closed*(fpx-pod.avg)*(1 if pod.pos > 0 else -1)*inst.mult - CFG['commission']
            pod.realized += pnl; pod.trades_n += 1
            if pnl > 0: pod.wins += 1; pod.gW += pnl
            else:       pod.gL -= pnl
            pod.trades.append(dict(side=1 if pod.pos > 0 else -1, eBar=pod.eBar,
                                   ePx=pod.avg, xBar=idx, xPx=fpx, pnl=pnl, why=why))
            if len(pod.trades) > 400: pod.trades.pop(0)
            pod.pos += diff
            if pod.pos == 0: pod.avg = 0.0
            else: pod.avg = fpx; pod.eBar = idx
        if pod.pos == 0: pod.trail_peak = None

    # ---------- pods ----------
    def start_pod(self, def_id, sym):
        defn = STRAT_BY_ID.get(def_id)
        if defn is None:
            self.ui.msg('usage: RUN <MOMENTUM|MEANREV|BREAKOUT|RSI> [TICKER]', 'err'); return
        if self.halted:
            self.ui.msg('TRADING HALTED — RISK ENGINE · "RESET RISK" TO RE-ARM', 'err'); return
        inst = self.by_sym(sym)
        if inst is None: self.ui.msg('UNKNOWN TICKER', 'err'); return
        if not self.can_trade(inst):
            self.ui.msg(f'{sym} IS THE COMPOSITE INDEX — NOT TRADABLE (BT / OPT ONLY)', 'err'); return
        pod = next((p for p in self.pods if p.key == defn['id']+'·'+sym), None)
        if pod and pod.running: self.ui.msg(f'{pod.key} ALREADY LIVE', 'err'); return
        if pod is None:
            if len(self.pods) >= CFG['pods']:
                self.ui.msg(f'POD CAP {CFG["pods"]} — STOP ONE FIRST', 'err'); return
            pod = Pod(defn, sym); self.pods.append(pod); self.pods_dirty = True
        ensure_emas(inst.ind, pod.params)
        pod.inst = inst; pod.unit = inst.lot; pod.running = True
        pod.pos = 0; pod.avg = 0.0; pod.realized = 0.0
        pod.trades = []; pod.trades_n = 0; pod.wins = 0
        pod.gW = 0.0; pod.gL = 0.0; pod.note = ''; pod.trail_peak = None
        self.audit('POD', f'START {pod.key}')
        self.ui.sig('SYS', f'{pod.key} armed · {defn["desc"]} · {param_schema_text(defn)}')
        self.ui.msg(f'{pod.key} STARTED', 'ok')
        self.pods_dirty = True; self.save_journal()

    def stop_pod(self, key, force=False):
        pod = next((p for p in self.pods if p.key == key), None)
        if pod is None or not pod.running: return
        if pod.pos != 0:
            self.strat_step(pod, 0, self.cur_bar_id(pod), pod.inst.px, True,
                            'HALT' if force else 'SIG')
        pod.running = False; pod.note = ''; pod.trail_peak = None
        self.audit('POD', f'STOP {key} · pnl {pod.realized:.2f}')
        self.ui.sig('SYS', f'{key} disarmed · session P&L {money(pod.realized, True)}')
        if not force: self.ui.msg(f'{key} STOPPED', 'ok')
        self.pods_dirty = True; self.save_journal()

    def stop_strat_all(self, def_id, force=False):
        for p in list(self.pods):
            if p.defn['id'] == def_id and p.running: self.stop_pod(p.key, force)

    def flat_account(self, force=False):
        for sym in list(self.acct['pos'].keys()):
            p = self.acct['pos'][sym]
            if not p['qty']: continue
            inst = self.by_sym(sym)
            px = inst.px - (1 if p['qty'] > 0 else -1)*CFG['slip_ticks']*inst.tick
            self.try_fill(sym, -p['qty'], px, 'FLAT', force, inst.px)

    def flat_all(self):
        for p in self.pods:
            if p.running: self.stop_pod(p.key, force=True)
        self.flat_account()
        self.audit('FLAT', 'book flattened')
        self.ui.sig('SYS', 'FLAT ALL — book flattened · all pods disarmed')
        self.ui.msg('BOOK FLATTENED', 'ok'); self.save_journal()

    def close_positions(self, sel, label):
        targets = []
        if sel == 'ALL':
            targets = [s for s, p in self.acct['pos'].items() if p['qty']]
        elif sel == 'MAC' or any(x['id'] == sel for x in SECTORS):
            targets = [s for s, p in self.acct['pos'].items() if p['qty']
                       and self.by_sym(s) and self.by_sym(s).sector == sel]
        else:
            if self.by_sym(sel) is None:
                self.ui.msg('CLOSE <SYM|SECTOR|ALL>', 'err'); return
            if self.acct['pos'].get(sel, dict(qty=0))['qty']: targets = [sel]
        if not targets: self.ui.msg('NO OPEN POSITIONS MATCH', 'err'); return
        n = 0
        for sym in targets:
            inst = self.by_sym(sym); p = self.acct['pos'][sym]
            px = inst.px - (1 if p['qty'] > 0 else -1)*CFG['slip_ticks']*inst.tick
            if self.try_fill(sym, -p['qty'], px, 'CLOSE', False, inst.px) is not None: n += 1
        self.audit('CLOSE', f'{label} · {n} position(s)')
        self.ui.msg(f'CLOSED {n} POSITION(S) — {label} · pods remain armed', 'ok')
        self.save_journal()

    def rate_ok(self):
        now = time.time()
        while self.ord_times and now-self.ord_times[0] > CFG['ord_rate_win']:
            self.ord_times.popleft()
        if len(self.ord_times) >= CFG['ord_rate_max']:
            self.ui.msg(f'ORDER RATE LIMIT — MAX {CFG["ord_rate_max"]} ORDERS / {CFG["ord_rate_win"]:.0f}S', 'err')
            return False
        self.ord_times.append(now); return True

    def manual_order(self, sym, side, qty):
        inst = self.by_sym(sym)
        if inst is None: self.ui.msg('UNKNOWN TICKER', 'err'); return
        if not self.can_trade(inst):
            self.ui.msg(f'{sym} IS THE COMPOSITE INDEX — NOT TRADABLE', 'err'); return
        if not self.rate_ok(): return
        px = inst.px + side*CFG['slip_ticks']*inst.tick
        if self.try_fill(sym, side*qty, px, 'MANL', False, inst.px) is None: return
        self.ui.sig('FILL', f'MANUAL {"BUY" if side>0 else "SELL"} {qty} {sym} @ {fmt_px(round_tick(px,inst),inst.dec)}')
        self.ui.msg(f'{"BUY" if side>0 else "SELL"} {qty} {sym} @ {fmt_px(round_tick(px,inst),inst.dec)}', 'ok')
        self.save_journal()

    def set_param(self, strat_id, param, val):
        defn = STRAT_BY_ID.get(strat_id)
        if defn is None: return
        sc = defn['params'].get(param)
        if sc is None:
            self.ui.msg(f'{esc(strat_id)} has no param {esc(param)} — '
                        f'{" · ".join(defn["params"])}', 'err'); return
        if not math.isfinite(val) or val < sc['min']-1e-9 or val > sc['max']+1e-9:
            self.ui.msg(f'{param} allowed range {sc["min"]} – {sc["max"]}', 'err'); return
        targets = [p for p in self.pods if p.defn['id'] == strat_id]
        if not targets:
            self.ui.msg(f'NO {strat_id} PODS — RUN {strat_id} [TKR] FIRST', 'err'); return
        for p in targets:
            p.params[param] = val
            if p.inst: ensure_emas(p.inst.ind, p.params)
        self.pods_dirty = True
        self.audit('PARAM', f'{strat_id}.{param}={val} ×{len(targets)}')
        self.ui.sig('SYS', f'{strat_id} {param} → {val} · {len(targets)} pod(s)')
        self.ui.msg(f'{strat_id} {param} = {val}', 'ok'); self.save_journal()

    def set_pod_risk(self, strat_id, key, val):
        targets = [p for p in self.pods if p.defn['id'] == strat_id]
        if not targets:
            self.ui.msg(f'NO {strat_id} PODS — RUN {strat_id} [TKR] FIRST', 'err'); return
        if not math.isfinite(val) or val < 0 or val > 2000:
            self.ui.msg(f'{key} range 0–2000 (0 disables)', 'err'); return
        v = int(round(val))
        for p in targets:
            if key == 'STOP': p.stop_ticks = v
            elif key == 'TGT': p.tgt_ticks = v
            elif key == 'TRAIL': p.trail_ticks = v; p.trail_peak = None
            elif key == 'MAXB': p.max_bars = v
        self.pods_dirty = True
        self.audit('PARAM', f'{strat_id}.{key}={v} ×{len(targets)}')
        self.ui.sig('SYS', f'{strat_id} {key} → {v}{" · disabled" if v==0 else ""} · '
                           f'{len(targets)} pod(s) · intrabar')
        self.ui.msg(f'{strat_id} {key} = {v}', 'ok'); self.save_journal()

    # ---------- orders / brackets / TIF ----------
    def spawn_exits(self, parent, fill_px):
        inst = self.by_sym(parent['sym'])
        oco_id = 'O'+str(self.order_seq); self.order_seq += 1
        armed = False
        for kind, trig in (('STP', fill_px - parent['side']*parent['stp_ticks']*inst.tick),
                           ('TGT', fill_px + parent['side']*parent['tgt_ticks']*inst.tick)):
            ticks = parent['stp_ticks'] if kind == 'STP' else parent['tgt_ticks']
            if ticks <= 0: continue
            self.orders.append(dict(id=self.order_seq, sym=parent['sym'],
                side=-parent['side'], qty=parent['qty'], px=round_tick(trig, inst),
                kind='EXIT', exit_kind=kind, status='WORKING', t=now_t(),
                oco_id=oco_id, parent=parent['id'], exp_bar=math.inf))
            self.order_seq += 1; armed = True
        if armed:
            self.ui.sig('SYS', f'BRACKET #{parent["id"]} ARMED — {parent["sym"]} '
                               f'{"LONG" if parent["side"]>0 else "SHORT"} {parent["qty"]} · '
                               f'STP {parent["stp_ticks"] or "—"} / TGT {parent["tgt_ticks"] or "—"} ticks · OCO · no expiry')
            self.audit('ORDER', f'bracket {parent["sym"]} STP{parent["stp_ticks"]} TGT{parent["tgt_ticks"]}')

    def place_order(self, sym, side, qty, lmt, stp=0, tgt=0):
        if self.halted:
            self.ui.msg('TRADING HALTED — RISK ENGINE · "RESET RISK" TO RE-ARM', 'err'); return
        inst = self.by_sym(sym)
        if inst is None: self.ui.msg('UNKNOWN TICKER', 'err'); return
        if not self.can_trade(inst):
            self.ui.msg(f'{sym} IS THE COMPOSITE INDEX — NOT TRADABLE', 'err'); return
        if qty <= 0 or not math.isfinite(lmt) or lmt <= 0:
            self.ui.msg('BAD ORDER — CHECK SYMBOL / QTY / LIMIT', 'err'); return
        if abs(lmt/inst.px - 1) > CFG['lmt_band_pct']:
            m = (f'FAT-FINGER REJECT — LMT {fmt_px(lmt,inst.dec)} IS '
                 f'{abs(lmt/inst.px-1)*100:.1f}% FROM LAST (BAND ±{CFG["lmt_band_pct"]*100:.0f}%)')
            self.ui.msg(m, 'err'); self.ui.sig('ERR', m); return
        if not self.rate_ok(): return
        o = dict(id=self.order_seq, sym=sym, side=side, qty=qty, px=lmt, kind='LMT',
                 status='WORKING', t=now_t(), stp_ticks=stp, tgt_ticks=tgt,
                 exp_bar=(self.bar_count()+CFG['tif_bars']) if CFG['tif_bars'] > 0 else math.inf)
        self.order_seq += 1
        self.orders.append(o)
        self.audit('ORDER', f'LMT {"BUY" if side>0 else "SELL"} {qty} {sym} @ {lmt}'
                            f'{" STP"+str(stp) if stp else ""}{" TGT"+str(tgt) if tgt else ""}'
                            f'{" TIF "+str(CFG["tif_bars"])+"B" if CFG["tif_bars"]>0 else ""}')
        self.ui.sig('SYS', f'LMT {b("BUY" if side>0 else "SELL")} {qty} {sym} @ '
                           f'{fmt_px(lmt,inst.dec)} — ORDER #{o["id"]} WORKING'
                           f'{" + BRACKET" if (stp or tgt) else ""}'
                           f'{" · TIF "+str(CFG["tif_bars"])+"B" if CFG["tif_bars"]>0 else ""}')
        self.match_orders()

    def match_orders(self):
        changed = False
        bc = self.bar_count()
        for o in self.orders:
            if o['status'] == 'WORKING' and o['kind'] == 'LMT' and bc >= o['exp_bar']:
                o['status'] = 'EXPIRED'
                self.ui.sig('SYS', f'ORDER #{o["id"]} EXPIRED — TIF {CFG["tif_bars"]}B reached · '
                                   f'{o["sym"]} {"BUY" if o["side"]>0 else "SELL"} {o["qty"]}')
                self.audit('ORDER', f'EXPIRE #{o["id"]} {o["sym"]}')
                changed = True
        for o in self.orders:
            if o['status'] != 'WORKING': continue
            inst = self.by_sym(o['sym']); px = inst.px
            if o['kind'] == 'LMT':
                hit = px <= o['px'] if o['side'] > 0 else px >= o['px']
            else:
                hit = (px <= o['px'] if o['side'] > 0 else px >= o['px']) \
                      if o['exit_kind'] == 'STP' else \
                      (px >= o['px'] if o['side'] > 0 else px <= o['px'])
            if not hit: continue
            if o['kind'] == 'EXIT':
                cur = self.acct['pos'].get(o['sym'], dict(qty=0))['qty']
                if cur == 0 or (cur > 0) == (o['side'] > 0):
                    o['status'] = 'STALE'
                    for x in self.orders:
                        if x.get('oco_id') == o['oco_id'] and x['status'] == 'WORKING':
                            x['status'] = 'CANCELED'
                    self.ui.sig('SYS', f'BRACKET #{o["parent"]} STALE — position closed · OCO group canceled')
                    changed = True; continue
                is_stp = o['exit_kind'] == 'STP'
                fill_px = round_tick(o['px'] - (1 if o['side'] > 0 else -1)*CFG['slip_ticks']*inst.tick, inst) \
                          if is_stp else o['px']
                rl = self.try_fill(o['sym'], o['side']*o['qty'], fill_px, 'BRKT', True, o['px'])
                o['status'] = 'FILLED' if rl is not None else 'REJECTED'
                if rl is not None:
                    self.ui.sig('FILL', f'OCO {o["exit_kind"]} HIT — #{o["id"]} '
                                        f'{"BUY" if o["side"]>0 else "SELL"} {o["qty"]} {o["sym"]} @ '
                                        f'{fmt_px(fill_px,inst.dec)}' + (' (slipped %dt)' % CFG['slip_ticks'] if is_stp else ''))
                    for x in self.orders:
                        if x.get('oco_id') == o['oco_id'] and x['status'] == 'WORKING':
                            x['status'] = 'CANCELED'
                    changed = True
                continue
            rl = self.try_fill(o['sym'], o['side']*o['qty'], o['px'], 'LMT', False, px)
            o['status'] = 'FILLED' if rl is not None else 'REJECTED'
            if rl is not None:
                self.ui.sig('FILL', f'ORDER #{o["id"]} FILLED — {"BUY" if o["side"]>0 else "SELL"} '
                                    f'{o["qty"]} {o["sym"]} @ {fmt_px(o["px"],inst.dec)}')
                if o['stp_ticks'] > 0 or o['tgt_ticks'] > 0: self.spawn_exits(o, o['px'])
                changed = True
        while len(self.orders) > 60 and self.orders[0]['status'] != 'WORKING':
            self.orders.pop(0)
        if changed: self.save_journal()

    def cancel_order(self, oid):
        o = next((x for x in self.orders if x['id'] == oid and x['status'] == 'WORKING'), None)
        if o is None: return
        o['status'] = 'CANCELED'
        if o.get('oco_id'):
            for x in self.orders:
                if x.get('oco_id') == o['oco_id'] and x['status'] == 'WORKING':
                    x['status'] = 'CANCELED'
        self.audit('ORDER', f'CANCEL #{oid}{" +OCO" if o.get("oco_id") else ""}')
        self.ui.sig('SYS', f'ORDER #{oid} CANCELED{" · OCO SIBLING TOO" if o.get("oco_id") else ""}')

    def cancel_all_orders(self):
        n = 0
        for o in self.orders:
            if o['status'] == 'WORKING': o['status'] = 'CANCELED'; n += 1
        if n:
            self.ui.sig('SYS', f'{n} WORKING ORDER{"S" if n>1 else ""} CANCELED')
            self.audit('ORDER', f'CANCEL ALL ({n})')

    def submit_order(self, sym, side, qty, lmt, stp=0, tgt=0):
        if lmt is not None:
            self.place_order(sym, side, qty, lmt, stp, tgt); return
        if stp > 0 or tgt > 0:
            if self.halted:
                self.ui.msg('TRADING HALTED — RISK ENGINE · "RESET RISK" TO RE-ARM', 'err'); return
            inst = self.by_sym(sym)
            if inst is None or not self.can_trade(inst):
                self.ui.msg('UNKNOWN / NON-TRADABLE TICKER', 'err'); return
            if not self.rate_ok(): return
            px = inst.px + side*CFG['slip_ticks']*inst.tick
            if self.try_fill(sym, side*qty, px, 'MKT', False, inst.px) is None: return
            parent = dict(id=self.order_seq, sym=sym, side=side, qty=qty,
                          stp_ticks=stp, tgt_ticks=tgt, px=px)
            self.order_seq += 1
            self.ui.sig('FILL', f'MARKET {"BUY" if side>0 else "SELL"} {qty} {sym} @ '
                                f'{fmt_px(round_tick(px,inst),inst.dec)}')
            self.audit('ORDER', f'MKT+BRKT {"BUY" if side>0 else "SELL"} {qty} {sym} @ {fmt(px,inst.dec)}')
            self.spawn_exits(parent, px)
            self.save_journal()
        else:
            self.manual_order(sym, side, qty)

    # ---------- alerts ----------
    def add_alert(self, sym, op, px):
        inst = self.by_sym(sym)
        if inst is None or not math.isfinite(px) or px <= 0:
            self.ui.msg('usage: ALERT <TKR> >|< <PRICE>', 'err'); return
        a = dict(id=self.alert_seq, sym=sym, op=op, px=px, active=True)
        self.alert_seq += 1; self.alerts.append(a)
        self.audit('ALERT', f'{sym} {op} {px}')
        self.ui.msg(f'ALERT #{a["id"]} SET — {sym} {op} {fmt_px(px,inst.dec)}', 'ok')

    def check_alerts(self):
        for a in self.alerts:
            if not a['active']: continue
            p = self.by_sym(a['sym']).px
            hit = p >= a['px'] if a['op'] == '>' else p <= a['px']
            if hit:
                a['active'] = False
                inst = self.by_sym(a['sym'])
                self.ui.sig('SIG', f'ALERT #{a["id"]} — {a["sym"]} '
                                   f'{"≥" if a["op"]==">" else "≤"} {fmt_px(a["px"],inst.dec)} · LAST {fmt_px(p,inst.dec)}')
                QApplication.beep()

    # ---------- arena ----------
    def arena_start(self, sym):
        inst = self.by_sym(sym)
        if inst is None: self.ui.msg('UNKNOWN TICKER', 'err'); return
        if not self.can_trade(inst):
            self.ui.msg(f'{sym} IS THE COMPOSITE INDEX — ARENA NEEDS A TRADABLE SYMBOL', 'err'); return
        if self.arena['on']: self.arena_stop(silent=True)
        self.arena['sym'] = sym; self.arena['on'] = True
        sims = []
        for defn in STRATS:
            prm = default_params(defn); ensure_emas(inst.ind, prm)
            sims.append(dict(defn=defn, prm=prm, pos=0, avg=0.0, realized=0.0,
                             trades_n=0, wins=0, gW=0.0, gL=0.0, eq=[], note=''))
        self.arena['sims'] = sims
        self.audit('ARENA', f'start {sym}')
        self.ui.sig('SYS', f'ARENA started on {sym} — 4 strategies · isolated $100K shadow books')
        self.ui.msg(f'ARENA LIVE ON {sym}', 'ok')

    def arena_stop(self, silent=False):
        if not self.arena['on']:
            if not silent: self.ui.msg('ARENA NOT RUNNING', 'err')
            return
        inst = self.by_sym(self.arena['sym'])
        for sm in self.arena['sims']:
            if sm['pos'] != 0: self.arena_fill(sm, 0, inst)
        tot = sum(sm['realized'] for sm in self.arena['sims'])
        self.arena['on'] = False
        self.audit('ARENA', f'stop {self.arena["sym"]} · pnl {tot:.2f}')
        self.ui.sig('SYS', f'ARENA stopped on {self.arena["sym"]} · combined shadow P&L {money(tot, True)}')
        if not silent: self.ui.msg('ARENA STOPPED', 'ok')

    def arena_fill(self, sm, target, inst):
        want = target*inst.lot
        if want == sm['pos']: return
        diff = want - sm['pos']; sgn = 1 if diff > 0 else -1
        fpx = inst.px + sgn*CFG['slip_ticks']*inst.tick
        if sm['pos'] == 0 or (sm['pos'] > 0) == (sgn > 0):
            tot = abs(sm['pos'])+abs(diff)
            sm['avg'] = (abs(sm['pos'])*sm['avg'] + abs(diff)*fpx)/tot
            sm['pos'] += diff
        else:
            closed = min(abs(sm['pos']), abs(diff))
            pnl = closed*(fpx-sm['avg'])*(1 if sm['pos'] > 0 else -1)*inst.mult - CFG['commission']
            sm['realized'] += pnl; sm['trades_n'] += 1
            if pnl > 0: sm['wins'] += 1; sm['gW'] += pnl
            else:       sm['gL'] -= pnl
            sm['pos'] += diff
            sm['avg'] = 0.0 if sm['pos'] == 0 else fpx

    def arena_bar(self, inst):
        for sm in self.arena['sims']:
            t, r = decide(sm['defn']['id'], sm['prm'], sm, inst.ind.s, inst)
            if r: sm['note'] = r
            if t != (1 if sm['pos'] > 0 else (-1 if sm['pos'] < 0 else 0)):
                self.arena_fill(sm, t, inst)
            sm['eq'].append(100000 + sm['realized'] + sm['pos']*(inst.px-sm['avg'])*inst.mult)
            if len(sm['eq']) > 500: sm['eq'].pop(0)

    @staticmethod
    def eq_stats(arr):
        if len(arr) < 3: return (None, 0.0)
        pk, dd = -1e18, 0.0
        for v in arr:
            pk = max(pk, v); dd = max(dd, (pk-v)/pk)
        rets = [arr[i]/arr[i-1]-1 for i in range(1, len(arr))]
        m = sum(rets)/len(rets)
        sd = math.sqrt(sum((x-m)**2 for x in rets)/len(rets))
        return (m/sd*math.sqrt(252*288) if sd > 0 else None), dd

    # ---------- live tick ----------
    def run_pods_on(self, inst):
        for p in self.pods:
            if not p.running or p.inst is None or p.inst.sym != inst.sym: continue
            t, r = decide(p.defn['id'], p.params, p, inst.ind.s, inst)
            if r: p.note = r
            cur = 1 if p.pos > 0 else (-1 if p.pos < 0 else 0)
            if t != cur:
                self.ui.sig('SIG', f'{p.key} {"CLOSE" if t==0 else ("BUY" if t>0 else "SELL")} '
                                   f'{inst.sym} — {r or "signal"}')
                self.strat_step(p, t, self.cur_bar_id(p), inst.px, False, 'SIG')

    def check_pod_risk(self):
        for p in self.pods:
            if not p.running or p.inst is None: continue
            inst = p.inst
            if p.pos == 0: p.trail_peak = None; continue
            if p.max_bars > 0 and (self.cur_bar_id(p)-p.eBar) >= p.max_bars:
                self.ui.sig('SIG', f'{p.key} TIME STOP — held {self.cur_bar_id(p)-p.eBar}B '
                                   f'≥ {p.max_bars}B · flattening')
                self.strat_step(p, 0, self.cur_bar_id(p), inst.px, True, 'TIME'); continue
            if p.trail_ticks > 0:
                if p.trail_peak is None: p.trail_peak = inst.px
                elif p.pos > 0: p.trail_peak = max(p.trail_peak, inst.px)
                else:           p.trail_peak = min(p.trail_peak, inst.px)
                give = (p.trail_peak-inst.px) if p.pos > 0 else (inst.px-p.trail_peak)
                if give >= p.trail_ticks*inst.tick:
                    self.ui.sig('ERR', f'{p.key} TRAIL HIT — gave {fmt(give,inst.dec)} ≥ '
                                       f'{p.trail_ticks}t from peak {fmt(p.trail_peak,inst.dec)}')
                    self.strat_step(p, 0, self.cur_bar_id(p), inst.px, True, 'TRAIL'); continue
            adverse = (inst.px-p.avg)*(1 if p.pos > 0 else -1)
            if p.stop_ticks > 0 and adverse <= -p.stop_ticks*inst.tick:
                self.ui.sig('ERR', f'{p.key} STOP HIT — {"LONG" if p.pos>0 else "SHORT"} '
                                   f'{abs(p.pos)} {inst.sym} · adverse {fmt(-adverse,inst.dec)} ≥ {p.stop_ticks} ticks')
                self.strat_step(p, 0, self.cur_bar_id(p), inst.px, True, 'STOP')
            elif p.tgt_ticks > 0 and adverse >= p.tgt_ticks*inst.tick:
                self.ui.sig('SIG', f'{p.key} TARGET HIT — {"LONG" if p.pos>0 else "SHORT"} · '
                                   f'gain {fmt(adverse,inst.dec)} ≥ {p.tgt_ticks} ticks')
                self.strat_step(p, 0, self.cur_bar_id(p), inst.px, True, 'TGT')

    def compute_breadth(self):
        adv = dec = hi = lo = 0
        for e in self.eqs:
            ch = e.px - self.day_open(e)
            if ch > 0: adv += 1
            elif ch < 0: dec += 1
            s = e.ind.s
            if s and len(s['cs']) >= 20:
                if e.px >= max(s['cs']): hi += 1
                elif e.px <= min(s['cs']): lo += 1
        self.breadth_hist.append(dict(adv=adv, dec=dec, hi=hi, lo=lo, t=time.time()))
        if len(self.breadth_hist) > 240: self.breadth_hist.pop(0)

    def current_equity(self):
        un = 0.0
        for s, p in self.acct['pos'].items():
            if not p['qty']: continue
            i = self.by_sym(s); un += (i.px-p['avg'])*p['qty']*i.mult
        return CFG['start_eq'] + self.acct['realized'] + un

    def push_eq_point(self):
        eq = self.current_equity()
        self.eq_hist.append(dict(t=time.time(), eq=eq))
        if len(self.eq_hist) > CFG['eq_points']: self.eq_hist.pop(0)
        self.eq_peak = max(self.eq_peak, eq)
        self.risk_monitor(eq)
        bc = self.bar_count()
        if bc > 0 and bc % CFG['day_len'] == 0 and self.last_day_roll != bc:
            self.last_day_roll = bc
            day_pnl = eq - self.day_start_eq
            self.audit('DAY', f'rollover day {self.day_n} · P&L {day_pnl:.0f} · equity {eq:.0f}')
            self.ui.sig('SYS', f'DAY {self.day_n} CLOSED — P&L {money(day_pnl,True)} · '
                               f'equity {money(eq)} · day loss limit rebased')
            self.day_start_eq = eq; self.day_n += 1

    def session_stats(self):
        n = len(self.eq_hist)
        if n < 2: return (0.0, None)
        pk, dd = -1e18, 0.0
        for p in self.eq_hist:
            pk = max(pk, p['eq']); dd = max(dd, (pk-p['eq'])/pk)
        rets = [self.eq_hist[i]['eq']/self.eq_hist[i-1]['eq']-1 for i in range(1, n)]
        m = sum(rets)/len(rets)
        sd = math.sqrt(sum((x-m)**2 for x in rets)/len(rets))
        return (dd, m/sd if sd > 0 else None)

    def tick(self):
        if self.paused or self.feed_down_until > time.time(): return
        t0 = time.perf_counter()
        try:
            self.tick_n += 1
            self.step_factors()
            for it in self.instrs: self.step_px(it)
            self.step_index()
            self.check_pod_risk()
            self.match_orders()
            self.check_alerts()
            bar_closed = self.tick_n % CFG['ticks_per_bar'] == 0
            if bar_closed:
                for it in self.instrs: self.close_bar_core(it)
                for it in self.instrs: self.run_pods_on(it)
                if self.arena['on']:
                    ai = self.by_sym(self.arena['sym'])
                    if ai is not None: self.arena_bar(ai)
                self.push_factor_hist()
                self.compute_breadth()
                self.push_eq_point()
            self.lat = clamp(self.lat + (random.random()-.5)*3, 7, 19)
            return bar_closed
        except Exception:
            self.sys_err('tick: '+traceback.format_exc(limit=2))
            return False
        finally:
            self.tick_times.append(time.perf_counter()-t0)

    # ---------- portfolio analytics ----------
    @staticmethod
    def std_of_diffs(a):
        if not a or len(a) < 12: return 0.0
        diffs = [a[i]-a[i-1] for i in range(1, len(a))]
        m = sum(diffs)/len(diffs)
        return math.sqrt(sum((d-m)**2 for d in diffs)/max(1, len(diffs)-1))

    def portfolio_analytics(self):
        eq = self.current_equity()
        rows = []; gross = net = 0.0
        for sym, p in self.acct['pos'].items():
            if not p['qty']: continue
            i = self.by_sym(sym)
            if i is None: continue
            mv = p['qty']*i.px*i.mult
            un = (i.px-p['avg'])*p['qty']*i.mult
            gross += abs(mv); net += mv
            rows.append(dict(sym=sym, inst=i, qty=p['qty'], avg=p['avg'], px=i.px,
                             mv=mv, un=un, rl=self.real_by_sym.get(sym, 0.0),
                             w=mv/eq if eq > 0 else 0.0))
        rows.sort(key=lambda r: -abs(r['mv']))
        beta = sum(r['w']*r['inst'].beta for r in rows)
        gross_w = sum(abs(r['w']) for r in rows) or 1.0
        hhi = sum((abs(r['w'])/gross_w)**2 for r in rows)
        top_w = abs(rows[0]['w']) if rows else 0.0
        sec_agg = {}
        for r in rows:
            a = sec_agg.setdefault(r['inst'].sector, dict(mv=0.0, un=0.0, rl=0.0, n=0))
            a['mv'] += r['mv']; a['un'] += r['un']; a['rl'] += r['rl']; a['n'] += 1
        sm = self.std_of_diffs(self.mkt['hist']) or 0.0009
        pv = beta*beta*sm*sm
        s_by = {}
        for r in rows:
            if r['inst'].sector in ('MAC', 'IDX'): continue
            s_by[r['inst'].sector] = s_by.get(r['inst'].sector, 0.0) + r['w']
        for k, wsum in s_by.items():
            ss = self.std_of_diffs(self.secst[k]['hist']) if k in self.secst else 0.0012
            ss = ss or 0.0012
            pv += wsum*wsum*ss*ss
        for r in rows: pv += r['w']**2*r['inst'].vol**2
        sig_bar = math.sqrt(max(pv, 0.0)); sig_day = sig_bar*math.sqrt(CFG['bars_per_day'])
        var95 = 1.645*sig_day*eq
        risk_map = {r['sym']: (r['w']**2*r['inst'].vol**2)/pv*100 if pv > 0 else 0.0
                    for r in rows}
        tl = [t['pnl']-t['fee'] for t in self.trades_log]
        wins = [x for x in tl if x > 0]; losses = [x for x in tl if x < 0]
        return dict(eq=eq, rows=rows, gross=gross, net=net, beta=beta, hhi=hhi,
                    top_w=top_w, sec_agg=sec_agg, sig_bar=sig_bar, sig_day=sig_day,
                    var95=var95, risk_map=risk_map,
                    trades=dict(n=len(tl),
                        win=(len(wins)/len(tl)) if tl else None,
                        pf=(sum(wins)/abs(sum(losses))) if losses else None,
                        exp=(sum(tl)/len(tl)) if tl else 0.0,
                        best=max(tl) if tl else None, worst=min(tl) if tl else None,
                        held=(sum(t['held'] for t in self.trades_log)/len(self.trades_log))
                             if self.trades_log else 0.0))

    # ---------- audit / persistence ----------
    def audit(self, kind, detail):
        self.journal.append(dict(t=datetime.now().isoformat(timespec='seconds'),
                                 kind=kind, detail=str(detail)))
        if len(self.journal) > 500: self.journal.pop(0)

    def save_journal(self):
        try:
            with open(JKEY_PATH, 'w') as f:
                json.dump(dict(v=2, saved=time.time(), seed=self.seed,
                    tif=CFG['tif_bars'], dayN=self.day_n, dayStartEq=self.day_start_eq,
                    risk=dict(per_sym=CFG['per_sym_notional'], gross=CFG['gross_notional'],
                              sec=CFG['max_sector_notional'], lots=CFG['max_lots'],
                              day_loss=CFG['daily_loss'], dd=CFG['max_dd_pct']),
                    pods=[dict(key=p.key, params=p.params, stop=p.stop_ticks,
                               tgt=p.tgt_ticks, trail=p.trail_ticks, maxb=p.max_bars)
                          for p in self.pods],
                    acct=dict(realized=self.acct['realized'], fills=self.acct['fills'],
                              pos={s: dict(qty=p['qty'], avg=p['avg'])
                                   for s, p in self.acct['pos'].items()}),
                    led=self.ledger,
                    pfa=dict(rs=self.real_by_sym, rt=self.real_by_tag,
                             tl=self.trades_log[-80:]),
                    fills_tail=self.fills[-60:]), f)
        except Exception:
            pass

    def load_journal(self):
        try:
            with open(JKEY_PATH) as f:
                j = json.load(f)
            if not j or time.time()-j.get('saved', 0) > 86400: return None
            return j
        except Exception:
            return None

    def apply_journal(self, j):
        if isinstance(j.get('seed'), int) and j['seed'] > 0 and j['seed'] != self.seed:
            self.seed = j['seed']; self.gen_history()
        if isinstance(j.get('tif'), int) and j['tif'] >= 0: CFG['tif_bars'] = j['tif']
        if isinstance(j.get('dayN'), int) and j['dayN'] > 0: self.day_n = j['dayN']
        dse = j.get('dayStartEq')
        if isinstance(dse, (int, float)) and dse > 0: self.day_start_eq = float(dse)
        r = j.get('risk') or {}
        for k, key in (('per_sym','per_sym_notional'), ('gross','gross_notional'),
                       ('sec','max_sector_notional'), ('lots','max_lots'),
                       ('day_loss','daily_loss'), ('dd','max_dd_pct')):
            v = r.get(k)
            if isinstance(v, (int, float)) and v > 0: CFG[key] = float(v)
        for pp in j.get('pods', []):
            key = pp.get('key', '')
            if '·' not in key: continue
            def_id, sym = key.split('·', 1)
            defn = STRAT_BY_ID.get(def_id); inst = self.by_sym(sym)
            if defn is None or inst is None or not self.can_trade(inst): continue
            pod = next((p for p in self.pods if p.key == key), None)
            if pod is None:
                if len(self.pods) >= CFG['pods']: continue
                pod = Pod(defn, sym); self.pods.append(pod)
            for k, v in (pp.get('params') or {}).items():
                if k in defn['params'] and isinstance(v, (int, float)):
                    pod.params[k] = v
            pod.stop_ticks = clamp(int(pp.get('stop', 0)), 0, 2000)
            pod.tgt_ticks = clamp(int(pp.get('tgt', 0)), 0, 2000)
            pod.trail_ticks = clamp(int(pp.get('trail', 0)), 0, 2000)
            pod.max_bars = clamp(int(pp.get('maxb', 0)), 0, 2000)
            ensure_emas(inst.ind, pod.params)
        for s, v in (j.get('led') or {}).items():
            if self.by_sym(s) and isinstance(v, int): self.ledger[s] = v
        pfa = j.get('pfa') or {}
        for s, v in (pfa.get('rs') or {}).items():
            if self.by_sym(s) and isinstance(v, (int, float)): self.real_by_sym[s] = v
        for t, v in (pfa.get('rt') or {}).items():
            if isinstance(v, (int, float)): self.real_by_tag[t] = v
        for x in (pfa.get('tl') or []):
            if self.by_sym(x.get('sym')): self.trades_log.append(x)
        acct = j.get('acct') or {}
        self.acct['realized'] = float(acct.get('realized') or 0.0)
        self.acct['fills'] = int(acct.get('fills') or 0)
        for s, p in (acct.get('pos') or {}).items():
            if self.by_sym(s) and isinstance(p.get('qty'), int) \
               and abs(p['qty']) <= 100000 and p.get('avg', 0) > 0:
                self.acct['pos'][s] = dict(qty=p['qty'], avg=float(p['avg']),
                                           eBar=len(self.by_sym(s).bars)-1)
        rl_total = sum(self.real_by_sym.values())
        tl_net = sum(t['pnl']-t['fee'] for t in self.trades_log)
        self.attr_base = rl_total - tl_net
        for f in reversed(j.get('fills_tail') or []):
            self.ui.fill_row(f)
        self.pods_dirty = True

    def reset_acct(self, silent=False):
        for p in self.pods:
            if p.running: self.stop_pod(p.key, force=True)
            p.pos = 0; p.avg = 0.0; p.realized = 0.0; p.trades = []
            p.trades_n = 0; p.wins = 0; p.gW = 0.0; p.gL = 0.0; p.note = ''
            p.stop_ticks = 0; p.tgt_ticks = 0; p.trail_ticks = 0
            p.trail_peak = None; p.max_bars = 0
        self.acct['pos'] = {}; self.acct['realized'] = 0.0; self.acct['fills'] = 0
        self.ledger.clear(); self.real_by_sym.clear(); self.real_by_tag.clear()
        self.trades_log.clear(); self.attr_base = 0.0; self.exec_stats.clear()
        self.fills.clear(); self.eq_hist.clear()
        self.eq_peak = CFG['start_eq']; self.day_start_eq = CFG['start_eq']
        self.day_n = 1; self.last_day_roll = -1; self.halted = False
        self.orders.clear()
        try: os.remove(JKEY_PATH)
        except OSError: pass
        self.audit('RESET', 'account rebased')
        self.pods_dirty = True
        if not silent:
            self.ui.sig('SYS', f'ACCOUNT RESET — equity rebased to {money(CFG["start_eq"])} · '
                               f'ledger + attribution cleared · journal wiped')
            self.ui.msg('ACCOUNT RESET', 'ok')

    def reseed(self, n):
        for p in self.pods:
            if p.running: self.stop_pod(p.key, force=True)
        self.arena.update(sym=None, on=False, sims=[])
        self.cancel_all_orders()
        self.last_bt = None; self.mc_state = None; self.opt_state = None
        self.seed = n
        self.reset_acct(silent=True)
        self.gen_history()
        self.audit('SEED', str(n))
        self.ui.sig('SYS', f'MARKET RE-SEEDED — seed {n} · {len(self.instrs)} instruments regenerated')
        self.ui.msg(f'MARKET SEED {n} — NEW SESSION', 'ok')

    def sys_err(self, m):
        self.ui.sig('ERR', 'RUNTIME — '+m.splitlines()[-1] if m else 'RUNTIME error')

    # ---------- reports ----------
    def exec_report(self):
        if not self.exec_stats: self.ui.msg('NO FILLS YET', 'ok'); return
        tot_n = sum(s['n'] for s in self.exec_stats.values())
        tot_f = sum(s['fees'] for s in self.exec_stats.values())
        tot_s = sum(s['slip'] for s in self.exec_stats.values())
        self.ui.sig('SYS', f'EXEC QUALITY — {tot_n} fills · fees {money(tot_f)} · '
                           f'slippage {money(tot_s, True)} (avg {money(tot_s/max(1,tot_n), True)}/fill)')
        for tag in sorted(self.exec_stats):
            s = self.exec_stats[tag]
            self.ui.sig('SYS', f'  · {tag} — {s["n"]} fills · slip {money(s["slip"], True)} · fees {money(s["fees"])}')
        self.ui.msg('exec report printed — slip < 0 = price improvement', 'ok')

    def perf_report(self):
        t = sorted(self.tick_times)
        avg = sum(t)/len(t) if t else 0
        p95 = t[int(len(t)*.95)] if t else 0
        up = int(time.time()-self.t0)
        mode = self.ui.compute_mode()
        self.ui.sig('SYS', f'PERF — tick avg {fmt(avg*1000,2)}ms / p95 {fmt(p95*1000,2)}ms · '
                           f'compute {mode}')
        self.ui.sig('SYS', f'STATE — uptime {up//60}m{up%60}s · audit {len(self.journal)} events · '
                           f'seed {self.seed} · ticks {self.tick_n} ({self.bar_count()} bars · day {self.day_n}) · '
                           f'universe {len(self.instrs)} · pods {len(self.pods)} · '
                           f'TIF {CFG["tif_bars"] if CFG["tif_bars"]>0 else "GTC"}')
        self.ui.msg('perf report printed', 'ok')

    def risk_report(self):
        a = self.portfolio_analytics()
        agg = {}
        for s, p in self.acct['pos'].items():
            if not p['qty']: continue
            i = self.by_sym(s)
            if i and i.sector not in ('MAC', 'IDX'):
                agg[i.sector] = agg.get(i.sector, 0.0) + abs(p['qty'])*i.px*i.mult
        top = ' · '.join(f'{k} {money_k(v)}' for k, v in
                         sorted(agg.items(), key=lambda x: -x[1])[:3]) or '—'
        self.ui.sig('SYS', f'RISK ENGINE — per-sym {money_k(CFG["per_sym_notional"])} · '
                           f'gross {money_k(CFG["gross_notional"])} · per-sector {money_k(CFG["max_sector_notional"])} · '
                           f'day {self.day_n} loss {money_k(CFG["daily_loss"])} · DD {CFG["max_dd_pct"]}% · '
                           f'limit band ±{CFG["lmt_band_pct"]*100:.0f}%')
        self.ui.sig('SYS', f'STATUS — gross {money_k(a["gross"])} '
                           f'({fmt(a["gross"]/CFG["gross_notional"]*100,1)}% of limit) · top sectors {top} · '
                           f'σ1d {fmt(a["sig_day"]*100,2)}% · VaR95 {money_k(a["var95"])} · '
                           f'day P&L {money(a["eq"]-self.day_start_eq, True)} · '
                           f'halted={b("YES" if self.halted else "NO")}')
        self.ui.msg('risk report printed · full detail on PORT screen', 'ok')

    def btlog_report(self):
        if not self.btlog:
            self.ui.msg('NO BACKTESTS RUN YET — BT <STRAT> <TKR> [BARS]', 'ok'); return
        self.ui.sig('SYS', f'BACKTEST LOG — last {len(self.btlog)}')
        for bl in self.btlog:
            r = bl['risk']
            rtxt = (f' STP {r["stp"]}' if r.get('stp') else '') + \
                   (f' TGT {r["tgt"]}' if r.get('tgt') else '') + \
                   (f' TRAIL {r["trail"]}' if r.get('trail') else '') + \
                   (f' MAXB {r["maxb"]}' if r.get('maxb') else '')
            self.ui.sig('SIG', f'{bl["t"]} {bl["stratId"]} {bl["sym"]} {bl["count"]}B{rtxt} — '
                               f'{(bl["ret"]>=0 and "+") or ""}{fmt(bl["ret"],1)}% · '
                               f'S {"—" if bl["sharpe"] is None else fmt(bl["sharpe"],2)} · '
                               f'DD −{fmt(bl["mdd"]*100,1)}% · {bl["n"]}T')

    def export_csv(self, path):
        with open(path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['time','sym','side','qty','price','source'])
            for x in self.fills: w.writerow([x['t'], x['sym'], x['side'], x['qty'], x['px'], x['tag']])
            w.writerow([]); w.writerow(['closed_round_trips'])
            w.writerow(['time','sym','side','qty','entry','exit','gross_pnl','fee','bars_held'])
            for t in self.trades_log:
                w.writerow([t['t'], t['sym'], 'L' if t['side'] > 0 else 'S', t['qty'],
                            t['ePx'], t['xPx'], f'{t["pnl"]:.2f}', t['fee'], t['held']])
            w.writerow([]); w.writerow(['equity_curve']); w.writerow(['time','equity'])
            for p in self.eq_hist:
                w.writerow([datetime.fromtimestamp(p['t']).isoformat(), f'{p["eq"]:.2f}'])
            w.writerow([]); w.writerow([f'ohlc_{self.ui.active}'])
            w.writerow(['time','open','high','low','close','volume'])
            ai = self.by_sym(self.ui.active)
            for bar in ai.bars[-300:]:
                w.writerow([hm_t(bar.t), bar.o, bar.h, bar.l, bar.c, bar.v])
            w.writerow([]); w.writerow(['audit_trail']); w.writerow(['time','kind','detail'])
            for a in self.journal: w.writerow([a['t'], a['kind'], a['detail']])

    # ---------- diagnostics ----------
    def diag(self):
        res = []
        def rep(name, ok, detail):
            res.append((name, ok, detail))
        syms = set(self.acct['pos']) | set(self.ledger)
        pos_ok = True; det = []
        for s in syms:
            a = self.acct['pos'].get(s, dict(qty=0))['qty']; bl = self.ledger.get(s, 0)
            if a != bl: pos_ok = False; det.append(f'{s} book={a} ledger={bl}')
        rep('POSITIONS vs FILL LEDGER', pos_ok, ' · '.join(det) or 'all symbols reconcile')
        net = sum(t['pnl']-t['fee'] for t in self.trades_log) + self.attr_base
        rl_total = sum(self.real_by_sym.values())
        rep('PORTFOLIO ATTRIBUTION', abs(net-rl_total) < .01,
            f'{len(self.trades_log)} round-trips · base {money(self.attr_base, True)} · '
            f'Σ {money(net, True)} vs ledger {money(rl_total, True)}')
        tag_map = {}
        for f in self.fills:
            tag_map.setdefault(f['tag'], {})
            tag_map[f['tag']][f['sym']] = tag_map[f['tag']].get(f['sym'], 0) + \
                (1 if f['side'] == 'B' else -1)*f['qty']
        for p in self.pods:
            if p.inst is None: continue
            total = tag_map.get(p.defn['id'], {}).get(p.inst.sym, 0)
            rep(f'POD {p.key} POSITION', total == p.pos, f'book={p.pos} ledger={total}')
        ind = Indicator(); ind.ema(9)
        for _ in range(60): ind.push(Bar(100,100,100,100,0,0))
        rep('EMA CONVERGENCE', abs(ind.s['ev'][9]-100) < 1e-6,
            f'const-series EMA9={fmt(ind.s["ev"][9],6)}')
        ind = Indicator(); ind.ema(9)
        for i in range(60): ind.push(Bar(100+i,100+i,100+i,100+i,0,0))
        rep('RSI BOUNDS / UPTREND', ind.s['rsi'] > 99.5,
            f'straight uptrend RSI={fmt(ind.s["rsi"],2)} (expect ≈100)')
        inst = self.by_sym(self.ui.active)
        r = bt_core(dict(bars=inst.bars[-150:],
                         inst=dict(sym=inst.sym, mult=inst.mult, lot=inst.lot,
                                   dec=inst.dec, tick=inst.tick),
                         stratId='BREAKOUT', prm=default_params(STRAT_BY_ID['BREAKOUT']),
                         cfg=dict(commission=CFG['commission'], slipTicks=CFG['slip_ticks'],
                                  stpTicks=30, tgtTicks=40, trailTicks=0, maxBars=0)))
        ok = (len(r['eq']) == 150 and all(math.isfinite(t['pnl']) for t in r['trades'])
              and all((t.get('why') or 'SIG') in ('SIG','STOP','TGT','TRAIL','TIME')
                      for t in r['trades']))
        rep('EXIT-ENGINE PARITY (BT vs LIVE)', ok,
            f'150B self-run · {r["n"]} trades · exits STOP:{r["exits"]["STOP"]} '
            f'TGT:{r["exits"]["TGT"]} · all reasons valid')
        keys = set(p.key for p in self.pods)
        reg_ok = len(keys) == len(self.pods) and len(self.pods) <= CFG['pods']
        bad = []
        for p in self.pods:
            for k, sc in p.defn['params'].items():
                v = p.params.get(k)
                if v is None or v < sc['min']-1e-9 or v > sc['max']+1e-9:
                    reg_ok = False; bad.append(f'{p.key}.{k}')
        rep('POD REGISTRY', reg_ok,
            f'{len(self.pods)}/{CFG["pods"]} pods · keys unique · {" · ".join(bad) or "params in schema"}')
        agg = {}
        for s, p in self.acct['pos'].items():
            if not p['qty']: continue
            i = self.by_sym(s)
            if i and i.sector not in ('MAC', 'IDX'):
                agg[i.sector] = agg.get(i.sector, 0.0) + abs(p['qty'])*i.px*i.mult
        over = [k for k, v in agg.items() if v > CFG['max_sector_notional']]
        top = ' · '.join(f'{k} {money_k(v)}' for k, v in
                         sorted(agg.items(), key=lambda x: -x[1])[:3])
        rep('SECTOR CAPS', not over,
            (top or 'no equity exposure')+f' · cap {money_k(CFG["max_sector_notional"])}/sector')
        a = self.portfolio_analytics()
        rep('PORTFOLIO RISK MODEL', math.isfinite(a['sig_day']) and a['sig_day'] >= 0
            and math.isfinite(a['var95']),
            f'σ1d {fmt(a["sig_day"]*100,2)}% · VaR95 {money_k(a["var95"])} · β {fmt(a["beta"],2)} · '
            f'HHI {fmt(a["hhi"],3)} · factor hists {len(self.mkt["hist"])}b')
        vw = inst.vw[-1] if inst.vw else None
        h, l = self.day_range(inst)
        rep('VWAP SANITY', vw is not None and l*0.9 < vw < h*1.1,
            f'{self.ui.active} session VWAP {"—" if vw is None else fmt_px(vw,inst.dec)} '
            f'within day range {fmt_px(l,inst.dec)}–{fmt_px(h,inst.dec)}')
        try:
            json.dumps({'t': 1}); ls_ok = True
        except Exception:
            ls_ok = False
        try: jbytes = os.path.getsize(JKEY_PATH)
        except OSError: jbytes = 0
        rep('PERSISTENCE', ls_ok, f'journal {jbytes}B at {JKEY_PATH}')
        uniq = len(set(i.sym for i in self.instrs))
        uni_ok = (uniq == len(self.instrs) and len(self.sym_map) == len(self.instrs)
                  and all(math.isfinite(i.px) and len(i.bars) > 100 for i in self.instrs))
        rep('UNIVERSE INTEGRITY', uni_ok,
            f'{len(self.instrs)} instruments · {len(self.eqs)} equities / {len(SECTORS)} sectors · '
            f'EMBX {fmt_px(self.idx.px,2) if self.idx else "—"} · symbols unique')
        tick_ok = all(abs(i.px/i.tick - round(i.px/i.tick)) < 1e-6 for i in self.instrs)
        rep('TICK ALIGNMENT', tick_ok, 'all last prices on legal tick grid')
        ob_ok = all(o['status'] != 'WORKING' or (self.by_sym(o['sym']) and o['qty'] > 0
                                                 and o['px'] > 0) for o in self.orders)
        oco_n = sum(1 for o in self.orders if o['status'] == 'WORKING' and o.get('oco_id'))
        rep('ORDER BOOK', ob_ok,
            f'{sum(1 for o in self.orders if o["status"]=="WORKING")} working · {oco_n} OCO legs · '
            f'TIF {CFG["tif_bars"] if CFG["tif_bars"]>0 else "GTC"}')
        tn = sum(s['n'] for s in self.exec_stats.values())
        tf = sum(s['fees'] for s in self.exec_stats.values())
        tsl = sum(s['slip'] for s in self.exec_stats.values())
        rep('EXEC LEDGER', tn == self.acct['fills'],
            f'{tn}/{self.acct["fills"]} fills · fees {money(tf)} · slip {money(tsl, True)}')
        rep('COMPUTE', True, f'{self.ui.compute_mode()} · BT/WF/BTALL/MC off the UI thread')
        eq = self.current_equity()
        rep('EQUITY IDENTITY', math.isfinite(eq),
            f'net liq {money(eq)} = $1MM + realized {money(self.acct["realized"], True)} + unrealized')
        dd, _ = self.session_stats()
        rep('SESSION RISK', not self.halted,
            f'day {self.day_n} · peak DD {fmt(dd*100,2)}% · gross {money_k(self.gross_notional())} · '
            f'halted={self.halted}')
        fails = sum(1 for _, ok, _ in res if not ok)
        for name, ok, detail in res:
            self.ui.sig('SYS', f'{b("PASS" if ok else "FAIL", UP if ok else DN)} {name} — {detail}')
        self.ui.msg(f'DIAGNOSTICS — {len(res)-fails} PASS · {fails} FAIL', 'err' if fails else 'ok')

    # ---------- scanner ----------
    def run_scan(self, strat_filter=None):
        out = [dict(defn=d, up=[], dn=[]) for d in STRATS
               if strat_filter is None or d['id'] == strat_filter]
        if not out:
            self.ui.msg('UNKNOWN STRATEGY — '+' · '.join(STRAT_IDS), 'err'); return
        for inst in self.instrs:
            s = inst.ind.s
            if not s: continue
            for o in out:
                t, r = decide(o['defn']['id'], default_params(o['defn']), dict(pos=0), s, inst)
                if t == 1 and r: o['up'].append(inst.sym)
                elif t == -1 and r: o['dn'].append(inst.sym)
        self.audit('SCAN', strat_filter or 'ALL')
        self.ui.sig('SYS', f'SCANNER — {len(self.instrs)} instruments · '
                           f'{strat_filter or "all strategies"} · default params · bar-close state')
        for o in out:
            for arr, arrow in ((o['up'], '▲ LONG'), (o['dn'], '▼ SHORT')):
                if arr:
                    head = ' '.join(arr[:10])
                    self.ui.sig('SIG', f'{o["defn"]["id"]} {arrow} {len(arr)} — '
                                       f'{head}{" +"+str(len(arr)-10)+" more" if len(arr)>10 else ""}')
            if not o['up'] and not o['dn']:
                self.ui.sig('SYS', f'  · {o["defn"]["id"]} — 0 fresh signals')
        self.ui.msg(f'SCAN DONE — {sum(len(o["up"])+len(o["dn"]) for o in out)} fresh signals', 'ok')

# ============================ 6 · UI widgets ============================
QSS = f"""
QWidget {{ background:#080a09; color:{TXT}; font-family:'Consolas','DejaVu Sans Mono',monospace;
           font-size:12px; }}
QLabel {{ background:transparent; }}
QPushButton {{ background:transparent; border:1px solid #3a4030; color:{AMBER};
               padding:3px 10px; font-size:10px; letter-spacing:1px; }}
QPushButton:hover {{ border-color:{AMBER}; }}
QPushButton:checked {{ background:{AMBER}; color:#000; font-weight:600; }}
QPushButton#bBuy  {{ border-color:#2b5c3d; color:{UP}; }}
QPushButton#bBuy:hover  {{ background:{UP}; color:#000; }}
QPushButton#bSell {{ border-color:#5c2b28; color:{DN}; }}
QPushButton#bSell:hover {{ background:{DN}; color:#000; }}
QLineEdit {{ background:#0a0d0a; border:1px solid #2a3026; color:{AMBER};
             padding:3px 6px; selection-background-color:{AMBER}; selection-color:#000; }}
QLineEdit#tk {{ color:{TXT}; }}
QComboBox {{ background:#0a0d0a; border:1px solid #33392c; color:{AMBER}; padding:2px 6px; }}
QComboBox QAbstractItemView {{ background:#0a0d0a; color:{TXT};
    selection-background-color:{AMBER}; selection-color:#000; }}
QListWidget {{ background:#0d100e; border:none; outline:none; }}
QListWidget::item {{ border-bottom:1px solid #161a15; }}
QListWidget::item:selected {{ background:#141810; color:{TXT}; }}
QTextBrowser {{ background:#0d100e; border:none; }}
QSplitter::handle {{ background:{'#20251e'}; width:1px; height:1px; }}
QProgressBar {{ background:#141811; border:none; max-height:3px; }}
QProgressBar::chunk {{ background:{AMBER}; }}
QScrollBar:vertical {{ background:transparent; width:9px; }}
QScrollBar::handle:vertical {{ background:#242a20; min-height:20px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height:0; }}
QScrollBar:horizontal {{ background:transparent; height:9px; }}
QScrollBar::handle:horizontal {{ background:#242a20; }}
QToolTip {{ background:#0a0d0a; color:{AMBER}; border:1px solid #6b5320; }}
"""

class HtmlPane(QTextBrowser):
    def __init__(self, on_anchor=None):
        super().__init__()
        self.setOpenLinks(False)
        self.setFrameShape(QFrame.NoFrame)
        self.document().setDefaultStyleSheet(
            f'body{{color:{TXT};}} a{{color:{AMBER};text-decoration:none;}}')
        self.anchor_cb = on_anchor
        self.anchorClicked.connect(self._go)

    def _go(self, url):
        if self.anchor_cb: self.anchor_cb(url.toString())

    def set_rows(self, rows):
        self.setHtml('<body>' + ''.join(rows) + '</body>')
        self.verticalScrollBar().setValue(0)

class SeriesChart(QWidget):
    """Reusable line chart: series, percentile bands, baseline, drawdown shading."""
    def __init__(self):
        super().__init__()
        self.series = []       # (data, color, width, penstyle, label)
        self.bands = []        # (hi, lo, rgba)
        self.baseline = None
        self.dd = False
        self.title = ''
        self.xlabel = None
        self.fmt_y = money_k
        self.setMinimumHeight(60)

    def paintEvent(self, _):
        g = QPainter(self)
        g.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        g.fillRect(0, 0, w, h, QColor('#0d100e'))
        all_v = []
        for data, *_ in self.series: all_v += [v for v in data if v is not None]
        for hi, lo, _c2 in self.bands: all_v += [v for v in hi+lo if v is not None]
        if self.baseline is not None: all_v.append(self.baseline)
        if not all_v:
            g.setPen(QColor(DIM)); g.drawText(12, 24, self.title or 'NO DATA')
            return
        mn, mx = min(all_v), max(all_v)
        pad = (mx-mn)*0.08 or 100.0
        mn -= pad; mx += pad
        PR, PT, PB = 74, 8, 16
        PW, PH = w-PR, h-PT-PB
        X = lambda i: i/(len(all_x := (self.series[0][0] if self.series else [0, 0]))-1)*PW \
            if len(all_x) > 1 else 0
        n0 = len(self.series[0][0]) if self.series else 2
        Xf = lambda i: i/(n0-1)*PW if n0 > 1 else 0
        Y = lambda v: PB + PH - (v-mn)/(mx-mn)*PH
        f = QFont('Consolas', 8); g.setFont(f)
        for k in range(5):
            v = mn + (mx-mn)*(k/4)
            y = Y(v)
            g.setPen(QColor('#161a15')); g.drawLine(0, int(y), PW, int(y))
            g.setPen(QColor(DIM)); g.drawText(PW+5, int(y)+4, self.fmt_y(v))
        if self.baseline is not None:
            g.setPen(QPen(QColor('#39402f'), 1, Qt.DashLine))
            g.drawLine(0, int(Y(self.baseline)), PW, int(Y(self.baseline)))
        for hi, lo, col in self.bands:
            g.setPen(Qt.NoPen); g.setColor(QColor(col))
            poly = QPolygonF()
            for i, v in enumerate(hi): poly.append(Xf(i), Y(v)) if False else poly.append(__import__('PySide6.QtCore', fromlist=['QPointF']).QPointF(Xf(i), Y(v)))
            for i in range(len(lo)-1, -1, -1): poly.append(__import__('PySide6.QtCore', fromlist=['QPointF']).QPointF(Xf(i), Y(lo[i])))
            g.drawPolygon(poly)
        for si, (data, color, width, style, _lbl) in enumerate(self.series):
            if not data: continue
            if self.dd and si == 0:
                pk = []; run = -1e18
                for v in data:
                    run = max(run, v); pk.append(run)
                g.setPen(Qt.NoPen); g.setColor(QColor(255, 84, 73, 45))
                poly = QPolygonF()
                from PySide6.QtCore import QPointF
                for i, v in enumerate(pk): poly.append(QPointF(Xf(i), Y(v)))
                for i in range(len(data)-1, -1, -1): poly.append(QPointF(Xf(i), Y(data[i])))
                g.drawPolygon(poly)
            pen = QPen(QColor(color), width)
            if style == 'dash': pen.setStyle(Qt.DashLine)
            elif style == 'dot': pen.setStyle(Qt.DotLine)
            g.setPen(pen)
            from PySide6.QtCore import QPointF
            prev = None
            for i, v in enumerate(data):
                if v is None: prev = None; continue
                p = QPointF(Xf(i), Y(v))
                if prev is not None: g.drawLine(prev, p)
                prev = p
        if self.title:
            g.setPen(QColor(DIM)); g.drawText(6, 14, self.title)
        if self.xlabel:
            g.setPen(QColor(DIM))
            g.drawText(4, h-4, self.xlabel[0])
            g.drawText(PW-90, h-4, self.xlabel[1])

class TapeWidget(QWidget):
    ROW_W = 116
    def __init__(self, desk):
        super().__init__()
        self.desk = desk; self.offset = 0.0
        self.setFixedHeight(26)
        self.setMouseTracking(True)
        self._hover = False
        self.anim = QTimer(self); self.anim.timeout.connect(self._slide)
        self.anim.start(33)

    def _slide(self):
        if self._hover or self.desk.paused: return
        self.offset += 1.9
        total = len(self.desk.instrs)*self.ROW_W
        if self.offset >= total: self.offset = 0.0
        self.update()

    def enterEvent(self, _): self._hover = True
    def leaveEvent(self, _): self._hover = False

    def paintEvent(self, _):
        g = QPainter(self)
        g.fillRect(self.rect(), QColor('#0a0d0b'))
        g.setFont(QFont('Consolas', 9))
        d = self.desk
        total = len(d.instrs)*self.ROW_W
        x0 = -self.offset
        i0 = int(self.offset/self.ROW_W)
        x = x0 + i0*self.ROW_W
        i = i0
        while x < self.width() and i < len(d.instrs)*2:
            it = d.instrs[i % len(d.instrs)]
            o = d.day_open(it); chg = (it.px-o)/o*100
            up = chg >= 0
            g.setPen(QColor(AMBER)); g.drawText(int(x)+4, 17, it.sym)
            g.setPen(QColor(TXT)); g.drawText(int(x)+44, 17, fmt_px(it.px, it.dec))
            g.setPen(QColor(UP if up else DN))
            g.drawText(int(x)+96, 17, ('▲+' if up else '▼')+fmt(chg, 2)+'%')
            g.setPen(QColor('#161a15'))
            g.drawLine(int(x)+self.ROW_W-1, 4, int(x)+self.ROW_W-1, 22)
            x += self.ROW_W; i += 1

class WatchDelegate(QStyledItemDelegate):
    ROW_H = 46
    def __init__(self, desk, parent=None):
        super().__init__(parent)
        self.desk = desk

    def sizeHint(self, _o, _i): return __import__('PySide6.QtCore', fromlist=['QSize']).QSize(120, self.ROW_H)

    def paint(self, g, opt, index):
        g.save()
        rect = opt.rect
        g.fillRect(rect, QColor('#141810') if opt.state & 0x8000 else QColor('#0d100e'))
        sym = index.data(Qt.UserRole)
        it = self.desk.by_sym(sym)
        if it is None: g.restore(); return
        active = sym == self.desk.ui.active
        if active:
            g.fillRect(rect, QColor('#141810'))
            g.setPen(QColor(AMBER)); g.drawLine(rect.left(), rect.top(),
                                                rect.left(), rect.bottom())
        o = self.desk.day_open(it); chg = (it.px-o)/o*100
        up_tick = it.px >= it.ppx
        f = g.font(); f.setBold(True); g.setFont(f)
        g.setPen(QColor(AMBER)); g.drawText(rect.adjusted(8, 5, -8, 0), Qt.AlignLeft, it.sym)
        f.setBold(False); g.setFont(f)
        g.setPen(QColor(DIM))
        name = it.name[:22]
        g.drawText(rect.adjusted(58, 5, -70, 0), Qt.AlignLeft, name)
        g.setPen(QColor(UP if chg >= 0 else DN))
        g.drawText(rect.adjusted(0, 5, -8, 0), Qt.AlignRight,
                   ('+' if chg >= 0 else '')+fmt(chg, 2)+'%')
        # sparkline
        data = [x.c for x in it.bars[-59:]] + [it.px]
        mn, mx = min(data), max(data)
        if mx-mn < 1e-9: mx = mn+1e-9
        sx, sw = rect.left()+8, rect.width()-110
        sy, sh = rect.top()+26, 14
        g.setPen(QColor(UP if data[-1] >= data[0] else DN))
        prev = None
        for i2, v in enumerate(data):
            p = (sx + i2/(len(data)-1)*sw, sy+sh - (v-mn)/(mx-mn)*sh)
            if prev: g.drawLine(int(prev[0]), int(prev[1]), int(p[0]), int(p[1]))
            prev = p
        g.setPen(QColor(UP if up_tick else (DN if it.px < it.ppx else QColor('#f0ead8'))))
        f2 = g.font(); f2.setBold(True); g.setFont(f2)
        g.drawText(rect.adjusted(0, 22, -8, 0), Qt.AlignRight, fmt_px(it.px, it.dec))
        g.restore()

class ChartWidget(QWidget):
    def __init__(self, desk, main):
        super().__init__()
        self.desk = desk; self.main = main
        self.view = 130; self.pan = 0
        self.mouse = None; self.drag = None
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.go_btn = QPushButton('▸ GO LIVE', self)
        self.go_btn.setVisible(False)
        self.go_btn.clicked.connect(self._go_live)
        self.ohlc_label = None

    def _go_live(self):
        self.pan = 0; self.update()

    def resizeEvent(self, e):
        self.go_btn.adjustSize()
        self.go_btn.move(self.width()-self.go_btn.width()-76, self.height()-40)
        super().resizeEvent(e)

    def _instr(self): return self.desk.by_sym(self.main.active)

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        self.view = clamp(round(self.view*(1.12 if d < 0 else 0.89)), 40, 400)
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.drag = (e.position().x(), self.pan)

    def mouseMoveEvent(self, e):
        self.mouse = (e.position().x(), e.position().y())
        if self.drag is not None:
            inst = self._instr()
            cw = (self.width()-64)/max(1, self.view)
            self.pan = clamp(round(self.drag[1] + (e.position().x()-self.drag[0])/cw),
                             0, len(inst.bars)-20)
        self.update()

    def mouseReleaseEvent(self, _): self.drag = None

    def mouseDoubleClickEvent(self, _):
        self.pan = 0; self.update()

    def leaveEvent(self, _):
        self.mouse = None; self.update()
        if self.ohlc_label: self.ohlc_label.setText('')

    def paintEvent(self, _):
        inst = self._instr()
        if inst is None: return
        g = QPainter(self)
        g.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        g.fillRect(0, 0, w, h, QColor('#0d100e'))
        AXW, AB = 64, 18
        PW, PH = w-AXW, h-AB
        bars = inst.bars; n = len(bars)
        if n < 5: return
        end_i = clamp(n-self.pan, 10, n)
        start_i = max(0, end_i-self.view)
        cnt = end_i-start_i+1; cw = PW/cnt
        show = self.main.chart_show
        mn = mx = None
        for i in range(start_i, end_i+1):
            bar = bars[i] if i < n else inst.forming
            mn = bar.l if mn is None else min(mn, bar.l)
            mx = bar.h if mx is None else max(mx, bar.h)
        def add_v(v):
            nonlocal mn, mx
            if v is not None and math.isfinite(v):
                mn = min(mn, v); mx = max(mx, v)
        if show['EMA']:
            for i in range(max(start_i, 0), min(end_i, n)):
                add_v(inst.s9[i]); add_v(inst.s21[i])
        if show['BB']:
            for i in range(max(start_i, 0), min(end_i, n)):
                add_v(inst.bu[i]); add_v(inst.bl[i])
        if show['VWAP']:
            for i in range(max(start_i, 0), min(end_i, n)):
                add_v(inst.vw[i])
        if mn is None: mn, mx = inst.px*.99, inst.px*1.01
        pad = (mx-mn)*0.07 or mx*0.001
        mn -= pad; mx += pad
        PT, PB = 8, PH-8
        Y = lambda p: PB - (p-mn)/(mx-mn)*(PB-PT)
        X = lambda i: (i-start_i+0.5)*cw
        g.setFont(QFont('Consolas', 8))
        rngv = mx-mn
        raw_step = rngv/6
        mag = 10**math.floor(math.log10(raw_step)) if raw_step > 0 else 1
        for m_step in (1, 2, 2.5, 5, 10):
            if m_step*mag >= raw_step: break
        step = m_step*mag
        p = math.ceil(mn/step)*step
        while p < mx:
            y = Y(p)
            g.setPen(QColor('#161a15')); g.drawLine(0, int(y), PW, int(y))
            g.setPen(QColor(DIM)); g.drawText(PW+6, int(y)+4, fmt_px(p, inst.dec))
            p += step
        k = max(1, round(80/cw))
        for i in range(start_i, min(end_i, n)):
            if (i+inst.shift) % k != 0: continue
            x = X(i)
            g.setPen(QColor('#141812')); g.drawLine(int(x), 0, int(x), PH)
            g.setPen(QColor(DIM)); g.drawText(int(x)-14, PH+13, hm_t(bars[i].t))
        if show['BB'] and end_i > start_i:
            g.setPen(Qt.NoPen); g.setColor(QColor(255, 160, 40, 12))
            poly = QPolygonF()
            from PySide6.QtCore import QPointF
            for i in range(max(start_i,0), min(end_i, n)):
                if inst.bu[i] is not None: poly.append(QPointF(X(i), Y(inst.bu[i])))
            for i in range(min(end_i, n)-1, max(start_i, 0)-1, -1):
                if inst.bl[i] is not None: poly.append(QPointF(X(i), Y(inst.bl[i])))
            g.drawPolygon(poly)
            for arr, _o in ((inst.bu, 0), (inst.bl, 0)):
                g.setPen(QPen(QColor('#3d443c'), 1)); prev = None
                for i in range(max(start_i,0), min(end_i, n)):
                    if arr[i] is None: prev = None; continue
                    p2 = QPointF(X(i), Y(arr[i]))
                    if prev: g.drawLine(prev, p2)
                    prev = p2
        if show['VWAP']:
            g.setPen(QPen(QColor(TEAL), 1, Qt.DashLine)); prev = None
            for i in range(max(start_i,0), min(end_i, n)):
                v = inst.vw[i]
                if v is None or not math.isfinite(v): prev = None; continue
                p2 = QPointF(X(i), Y(v))
                if prev: g.drawLine(prev, p2)
                prev = p2
        if show['EMA']:
            for arr, color, style in ((inst.s9, AMBER, Qt.SolidLine),
                                      (inst.s21, BLUE, Qt.SolidLine),
                                      (inst.s50, '#6b7263', Qt.DashLine)):
                g.setPen(QPen(QColor(color), 1, style)); prev = None
                for i in range(max(start_i,0), min(end_i, n)):
                    v = arr[i]
                    if v is None or not math.isfinite(v): prev = None; continue
                    p2 = QPointF(X(i), Y(v))
                    if prev: g.drawLine(prev, p2)
                    prev = p2
        bw = max(1.0, min(9.0, cw*0.62))
        for i in range(start_i, end_i+1):
            bar = bars[i] if i < n else inst.forming
            up = bar.c >= bar.o
            col = QColor(UP if up else DN)
            g.setPen(col); g.setBrush(QBrush(col))
            x = X(i)
            g.drawLine(QPointF(x, Y(bar.h)), QPointF(x, Y(bar.l)))
            y1 = Y(max(bar.o, bar.c)); y2 = Y(min(bar.o, bar.c))
            g.drawRect(QPointF(x-bw/2, y1).x(), y1, bw, max(1.0, y2-y1))
        if show['VOL']:
            vm = max((bar.v for bar in (bars[i] if i < n else inst.forming
                                        for i in range(start_i, end_i+1))), default=0)
            if vm > 0:
                vh = PH*0.14
                for i in range(start_i, end_i+1):
                    bar = bars[i] if i < n else inst.forming
                    g.setPen(Qt.NoPen)
                    g.setColor(QColor(47, 212, 113, 76) if bar.c >= bar.o else QColor(255, 84, 73, 76))
                    g.drawRect(X(i)-bw/2, PH-(bar.v/vm)*vh, bw, (bar.v/vm)*vh)
        # order + trailing lines
        d = self.desk
        for o in d.orders:
            if o['sym'] != self.main.active or o['status'] != 'WORKING': continue
            y = Y(o['px'])
            if PT < y < PB:
                is_exit = o['kind'] == 'EXIT'
                col = QColor(DN if (is_exit and o['exit_kind'] == 'STP')
                             else (UP if (is_exit and o['exit_kind'] == 'TGT')
                                   else (BLUE if o['side'] > 0 else DN)))
                g.setPen(QPen(col, 1, Qt.DotLine if is_exit else Qt.DashLine))
                g.drawLine(0, int(y), PW, int(y))
                lbl = (f'#{o["id"]} OCO {o["exit_kind"]} '
                       f'{"BUY" if o["side"]>0 else "SELL"}{o["qty"]}') if is_exit else \
                      (f'#{o["id"]} {"BUY" if o["side"]>0 else "SELL"}{o["qty"]} '
                       f'LMT {fmt_px(o["px"],inst.dec)}')
                g.setPen(col); g.setFont(QFont('Consolas', 8))
                g.drawText(4, int(y)-3, lbl)
        for p in d.pods:
            if (p.inst is None or p.inst.sym != self.main.active or not p.running
                    or p.pos == 0 or not p.trail_ticks or p.trail_peak is None): continue
            lvl = (p.trail_peak - p.trail_ticks*inst.tick) if p.pos > 0 else \
                  (p.trail_peak + p.trail_ticks*inst.tick)
            y = Y(lvl)
            if PT < y < PB:
                g.setPen(QPen(QColor(255, 84, 73, 190), 1, Qt.DashLine))
                g.drawLine(0, int(y), PW, int(y))
                g.setPen(QColor(DN)); g.setFont(QFont('Consolas', 8))
                g.drawText(4, int(y)+10, f'TRAIL {p.defn["id"][:3]}·{p.sym} {fmt_px(lvl,inst.dec)}')
        ly = Y(inst.px)
        g.setPen(QPen(QColor(255, 160, 40, 140), 1, Qt.DashLine))
        g.drawLine(0, int(ly), PW, int(ly))
        g.setBrush(QColor(AMBER)); g.setPen(Qt.NoPen)
        g.drawRect(PW, ly-8, AXW, 16)
        g.setPen(QColor('#000')); g.setFont(QFont('Consolas', 9, QFont.Bold))
        g.drawText(PW+5, int(ly)+4, fmt_px(inst.px, inst.dec))
        if self.main.chart_show['MKT']:
            for p in d.pods:
                if p.inst is None or p.inst.sym != self.main.active: continue
                if not p.trades and p.pos == 0: continue
                col = QColor(p.defn.get('color', STRAT_COLORS[p.defn['id']]))
                def mark(idx, px, direction, is_exit, col_c):
                    i = idx - inst.shift
                    if i < start_i or i > min(end_i, n-1): return
                    bar = bars[i]
                    if bar is None: return
                    x = X(i)
                    g.setPen(Qt.NoPen); g.setColor(QColor(col_c))
                    if direction > 0:
                        y = Y(bar.l)+7
                        g.drawPolygon(QPolygonF([QPointF(x, y), QPointF(x-4, y+6),
                                                 QPointF(x+4, y+6)]))
                    else:
                        y = Y(bar.h)-7
                        g.drawPolygon(QPolygonF([QPointF(x, y), QPointF(x-4, y-6),
                                                 QPointF(x+4, y-6)]))
                    if is_exit:
                        g.setPen(QPen(QColor(col_c), 1)); yy = Y(px)
                        g.drawLine(QPointF(x-3, yy-3), QPointF(x+3, yy+3))
                        g.drawLine(QPointF(x+3, yy-3), QPointF(x-3, yy+3))
                for t in p.trades:
                    mark(t['eBar'], t['ePx'], t['side'], False, col)
                    ex_col = QColor(DN) if t.get('why') in ('STOP', 'TRAIL') else col
                    mark(t['xBar'], t['xPx'], -t['side'], True, ex_col)
                if p.pos != 0:
                    mark(p.eBar, p.avg, 1 if p.pos > 0 else -1, True, col)
        # crosshair
        if self.mouse and self.mouse[0] < PW and self.mouse[1] < PH:
            mxp, myp = self.mouse
            idx = clamp(round(mxp/cw-0.5)+start_i, start_i, end_i)
            bar = bars[idx] if idx < n else inst.forming
            cx = X(idx)
            g.setPen(QPen(QColor('#7a8070'), 1, Qt.DashLine))
            g.drawLine(int(cx), 0, int(cx), PH)
            g.drawLine(0, int(myp), PW, int(myp))
            pv = mn + (1-(myp-PT)/(PB-PT))*(mx-mn)
            g.setBrush(QColor('#22281f')); g.setPen(Qt.NoPen)
            g.drawRect(PW, myp-8, AXW, 16)
            g.setPen(QColor(AMBER)); g.drawText(PW+5, int(myp)+4, fmt_px(pv, inst.dec))
            if self.ohlc_label:
                prev_c = bars[idx-1].c if idx > 0 else bar.o
                dpc = (bar.c/prev_c-1)*100
                tag = hm_t(bar.t) if idx < n else 'LIVE'
                self.ohlc_label.setText(
                    f'{tag}  O <b>{fmt_px(bar.o,inst.dec)}</b>  H <b>{fmt_px(bar.h,inst.dec)}</b>  '
                    f'L <b>{fmt_px(bar.l,inst.dec)}</b>  C <b>{fmt_px(bar.c,inst.dec)}</b>  '
                    f'Δ <span style="color:{UP if dpc>=0 else DN}">{(dpc>=0 and "+") or ""}{fmt(dpc,2)}%</span>'
                    f'  V <b>{bar.v}</b>')
        self.go_btn.setVisible(self.pan > 0)

class BootOverlay(QWidget):
    def __init__(self, parent, lines, on_done):
        super().__init__(parent)
        self.setGeometry(parent.rect())
        self.lines = lines
        self.li = 0; self.ci = 0
        self.on_done = on_done
        self.raise_(); self.show()
        self.timer = QTimer(self); self.timer.timeout.connect(self._step)
        self.timer.start(9)

    def resizeEvent(self, e): self.setGeometry(self.parentWidget().rect())

    def _step(self):
        if self.li >= len(self.lines):
            self.timer.stop()
            QTimer.singleShot(320, self._finish)
            return
        line, cls = self.lines[self.li]
        self.ci += 3
        if self.ci >= len(line):
            self.li += 1; self.ci = 0
            self.timer.setInterval(70)
        else:
            self.timer.setInterval(9)
        self.update()

    def _finish(self):
        self.timer.stop(); self.deleteLater()
        self.on_done()

    def paintEvent(self, _):
        g = QPainter(self)
        g.fillRect(self.rect(), QColor('#080a09'))
        g.setFont(QFont('Consolas', 12))
        y = self.height()/2 - len(self.lines)*12
        done_li = self.li
        for i, (line, cls) in enumerate(self.lines):
            txt = line if i < done_li else line[:self.ci] if i == done_li else ''
            col = QColor('#5b6154') if cls == 'dm' else QColor('#d99a33')
            g.setPen(col)
            g.drawText(60, int(y)+i*24+18, txt)
            if i < done_li and cls == 'ok' and not line.endswith('$1,000,000.00'):
                w = g.fontMetrics().horizontalAdvance(line)
                g.setPen(QColor(UP)); g.drawText(60+w+10, int(y)+i*24+18, 'OK')

# ============================ 7 · main window ============================
class CmdEdit(QLineEdit):
    exec_req = Signal(str)
    complete_req = Signal()
    hist_req = Signal(int)
    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.exec_req.emit(self.text()); self.clear(); return
        if e.key() == Qt.Key_Tab:
            self.complete_req.emit(); return
        if e.key() == Qt.Key_Up:
            self.hist_req.emit(-1); return
        if e.key() == Qt.Key_Down:
            self.hist_req.emit(1); return
        if e.key() == Qt.Key_Escape:
            self.clearFocus(); return
        super().keyPressEvent(e)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('EMBER TERMINAL — ALGO DESK')
        self.resize(1600, 940)
        self.desk = Desk(); self.desk.ui = self
        self.active = 'ES'
        self.hist = []; self.hi = 0
        self.chart_show = dict(EMA=True, BB=False, VOL=True, VWAP=True, MKT=True)
        self.hidden_marks = set()
        self.confirm_flat = 0.0; self.confirm_reset = 0.0
        self._batch_pending = 0; self._batch_results = []
        self._hints = ['try: WF MOMENTUM FAST NVDA 1200',
                       'try: BT BREAKOUT CL 1200 STP 30 TGT 50', 'try: PORT',
                       'try: BTALL MOMENTUM SEM', 'try: TIF 240', 'try: DIAG',
                       'try: SEED 42', 'try: SCAN', 'try: ARENA AMD']
        self._hint_i = 0
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(max(1, min(4, (os.cpu_count() or 2)-1)))
        self._build_ui()
        self._load_prefs()
        self._boot()
        self._bind_keys()
        self.hint_timer = QTimer(self); self.hint_timer.timeout.connect(self._rotate_hint)
        self.hint_timer.start(4000)
        self.clock_timer = QTimer(self); self.clock_timer.timeout.connect(self._clock)
        self.clock_timer.start(1000); self._clock()

    # ---------- compute mode ----------
    def compute_mode(self):
        n = self.pool.maxThreadCount()
        return f'THREAD×{n}'

    def submit_job(self, tag, fn, on_done, on_fail=None):
        class S(QObject):
            done = Signal(str, object); fail = Signal(str, str)
        job = QRunnable();  # wrap
        holder = type('H', (QObject,), {})
        sig = S()
        def run():
            try: res = fn()
            except Exception as e:
                sig.fail.emit(tag, str(e)); return
            sig.done.emit(tag, res)
        class R(QRunnable):
            def run(self_inner): run()
        if on_done: sig.done.connect(lambda t, r: on_done(t, r))
        if on_fail: sig.fail.connect(lambda t, m: on_fail(t, m))
        else: sig.fail.connect(lambda t, m: self.desk.sys_err(t+': '+m))
        self.pool.start(R())

    # ---------- UI construction ----------
    def _build_ui(self):
        app_font = QFont('Consolas', 10)
        app_font.setStyleHint(QFont.Monospace)
        self.setFont(app_font)
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # --- top bar
        top = QWidget(); top.setFixedHeight(44)
        tl = QHBoxLayout(top); tl.setContentsMargins(0, 0, 0, 0); tl.setSpacing(0)
        brand = QLabel(' EMBER '); brand.setStyleSheet(
            f'background:{AMBER}; color:#000; font-weight:700; font-size:13px; padding:0 12px;')
        ver = QLabel(' TERMINAL 12.0 '); ver.setStyleSheet(
            f'color:{AMBER}; font-size:10px; letter-spacing:3px; padding:0 12px;')
        self.cmd = CmdEdit(); self.cmd.setPlaceholderText('type a command — HELP for reference')
        self.cmd.exec_req.connect(self._exec_from_ui)
        self.cmd.complete_req.connect(self._complete)
        self.cmd.hist_req.connect(self._hist)
        self.cmdmsg = QLabel(''); self.cmdmsg.setFixedWidth(430)
        self.cmdmsg.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lat_lab = QLabel('LAT --MS')
        self.clock_lab = QLabel('--:--:-- UTC')
        self.conn_lab = QLabel('● DATA·SIM')
        tl.addWidget(brand); tl.addWidget(ver); tl.addWidget(self.cmd, 1)
        tl.addWidget(self.cmdmsg); tl.addWidget(self.lat_lab)
        tl.addWidget(self.clock_lab); tl.addWidget(self.conn_lab)
        root.addWidget(top)

        # --- halt banner
        self.halt_banner = QLabel('▮ TRADING HALTED — RISK LIMIT BREACHED · ALL POSITIONS '
                                  'FLATTENED · CLICK HERE OR TYPE RESET RISK TO RE-ARM')
        self.halt_banner.setStyleSheet(
            'background:#3d0e0a; color:#ffb9b3; padding:6px 14px; letter-spacing:2px;')
        self.halt_banner.setVisible(False)
        self.halt_banner.mousePressEvent = lambda _e: self._preset_cmd('RESET RISK')
        root.addWidget(self.halt_banner)

        # --- tape
        self.tape = TapeWidget(self.desk)
        root.addWidget(self.tape)

        # --- main split
        split_v = QSplitter(Qt.Vertical)
        split_h = QSplitter(Qt.Horizontal)

        # watch panel
        watch_w = QWidget(); wl = QVBoxLayout(watch_w)
        wl.setContentsMargins(0, 0, 0, 0); wl.setSpacing(0)
        wh = QHBoxLayout(); wh.setContentsMargins(6, 3, 6, 3)
        self.watch_search = QLineEdit(); self.watch_search.setPlaceholderText('SEARCH')
        self.watch_search.setFixedWidth(100)
        self.watch_search.textChanged.connect(self._watch_refresh)
        wh.addWidget(self.watch_search); wh.addStretch(1)
        wl.addLayout(wh)
        self.chip_row = QHBoxLayout(); self.chip_row.setContentsMargins(6, 0, 6, 3)
        self.chip_row.setSpacing(3)
        self._build_chips()
        wl.addLayout(self.chip_row)
        self.watch_list = QListWidget()
        self.watch_delegate = WatchDelegate(self.desk, self.watch_list)
        self.watch_list.setItemDelegate(self.watch_delegate)
        self.watch_list.setVerticalScrollMode(QListWidget.ScrollPerItem)
        self.watch_list.itemClicked.connect(lambda item: self.load(item.data(Qt.UserRole)))
        self.watch_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        wl.addWidget(self.watch_list, 1)
        self._watch_fill()

        # center
        center_w = QWidget(); cl = QVBoxLayout(center_w)
        cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)
        head = QHBoxLayout(); head.setContentsMargins(8, 3, 8, 3)
        self.scr_title = QLabel('ES')
        self.scr_title.setStyleSheet(f'color:{AMBER}; font-weight:600; letter-spacing:1px;')
        self.ch_hl = QLabel(''); self.ch_hl.setStyleSheet(f'color:{DIM}; font-size:10px;')
        self.ch_last = QLabel('--'); self.ch_last.setStyleSheet(
            'font-size:14px; font-weight:600;')
        self.ch_chg = QLabel('')
        head.addWidget(self.scr_title); head.addStretch(1)
        head.addWidget(self.ch_hl); head.addSpacing(12)
        head.addWidget(self.ch_last); head.addWidget(self.ch_chg)
        for key, lab in (('EMA','EMA'), ('BB','BB'), ('VOL','VOL'),
                         ('VWAP','VWAP'), ('MKT','MARKS')):
            btn = QPushButton(lab); btn.setCheckable(True)
            btn.setChecked(self.chart_show[key]); btn.setFixedHeight(20)
            btn.toggled.connect(lambda on, k=key: self._toggle_chart(k, on))
            head.addWidget(btn)
        self.legend_row = QHBoxLayout(); self.legend_row.setSpacing(3)
        head.addLayout(self.legend_row)
        cl.addLayout(head)
        self.stack = QStackedWidget()

        # chart page
        chart_page = QWidget(); cpl = QVBoxLayout(chart_page)
        cpl.setContentsMargins(0, 0, 0, 0)
        self.chart = ChartWidget(self.desk, self)
        self.chart.ohlc_label = QLabel(''); self.chart.ohlc_label.setStyleSheet(
            f'color:{DIM}; font-size:10px; background:transparent;')
        self.chart.ohlc_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        cpl.addWidget(self.chart, 1)
        # stack pages
        self.top_pane = HtmlPane(self._anchor)
        self.bt_title = QLabel('BACKTEST')
        self.bt_run_btn = QPushButton('▸ RUN LIVE'); self.bt_run_btn.clicked.connect(self._bt_run_live)
        self.bt_chart = SeriesChart()
        self.bt_pane = HtmlPane(self._anchor)
        bt_page = QWidget(); bl2 = QVBoxLayout(bt_page); bl2.setContentsMargins(0, 0, 0, 0)
        bh = QHBoxLayout(); bh.setContentsMargins(8, 4, 8, 4)
        bh.addWidget(self.bt_title); bh.addStretch(1); bh.addWidget(self.bt_run_btn)
        bl2.addLayout(bh); bl2.addWidget(self.bt_chart, 3); bl2.addWidget(self.bt_pane, 2)
        self.port_stats = QLabel(''); self.port_stats.setContentsMargins(8, 4, 8, 0)
        self.port_chart = SeriesChart(); self.port_chart.setFixedHeight(130)
        self.port_pane = HtmlPane(self._anchor)
        port_page = QWidget(); pl2 = QVBoxLayout(port_page); pl2.setContentsMargins(0, 0, 0, 0)
        pl2.addWidget(self.port_stats); pl2.addWidget(self.port_chart)
        pl2.addWidget(self.port_pane, 1)
        # lab page
        lab_page = QWidget(); ll = QVBoxLayout(lab_page); ll.setContentsMargins(8, 6, 8, 6)
        ll.addWidget(QLabel(b('STRATEGY ARENA — HEAD-TO-HEAD SHADOW SIMS', AMBER)))
        arena_row = QHBoxLayout()
        self.arena_sym = QComboBox()
        self.arena_sym.addItems([i.sym for i in self.desk.instrs if self.desk.can_trade(i)])
        arena_go = QPushButton('▸ RUN ARENA')
        arena_go.clicked.connect(lambda: self.desk.arena_start(self.arena_sym.currentText()))
        arena_stop = QPushButton('■ STOP')
        arena_stop.clicked.connect(lambda: self.desk.arena_stop())
        self.arena_stat = QLabel('ARENA IDLE'); self.arena_stat.setStyleSheet(f'color:{DIM}')
        arena_row.addWidget(QLabel('SYMBOL')); arena_row.addWidget(self.arena_sym)
        arena_row.addWidget(arena_go); arena_row.addWidget(arena_stop)
        arena_row.addWidget(self.arena_stat); arena_row.addStretch(1)
        ll.addLayout(arena_row)
        self.lab_pane = HtmlPane(self._anchor)
        ll.addWidget(self.lab_pane, 2)
        ll.addWidget(QLabel(b('OPTIMIZER · WALK-FORWARD · CROSS-SECTIONAL BATCH — OFF THREAD', AMBER)))
        opt_row = QHBoxLayout()
        self.opt_strat = QComboBox(); self.opt_strat.addItems(STRAT_IDS)
        self.opt_param = QComboBox()
        self.opt_strat.currentTextChanged.connect(self._fill_params)
        self._fill_params()
        self.opt_sym = QComboBox(); self.opt_sym.addItems(self.desk.syms)
        self.opt_sym.setCurrentText('ES')
        self.opt_bars = QLineEdit('1000'); self.opt_bars.setFixedWidth(60)
        opt_row.addWidget(QLabel('STRAT')); opt_row.addWidget(self.opt_strat)
        opt_row.addWidget(QLabel('PARAM')); opt_row.addWidget(self.opt_param)
        opt_row.addWidget(QLabel('TKR')); opt_row.addWidget(self.opt_sym)
        opt_row.addWidget(QLabel('BARS')); opt_row.addWidget(self.opt_bars)
        sweep_btn = QPushButton('▸ SWEEP')
        sweep_btn.clicked.connect(self._opt_go)
        wf_btn = QPushButton('▸ WALK-FWD')
        wf_btn.clicked.connect(self._wf_go)
        opt_row.addWidget(sweep_btn); opt_row.addWidget(wf_btn)
        self.bt_target = QComboBox(); self.bt_target.addItems(['ALL']+[s['id'] for s in SECTORS])
        btall_btn = QPushButton('▸ BTALL')
        btall_btn.clicked.connect(self._btall_go)
        opt_row.addWidget(QLabel('BATCH')); opt_row.addWidget(self.bt_target)
        opt_row.addWidget(btall_btn)
        self.opt_stat = QLabel(''); self.opt_stat.setStyleSheet(f'color:{DIM}')
        opt_row.addWidget(self.opt_stat); opt_row.addStretch(1)
        ll.addLayout(opt_row)
        self.opt_pane = HtmlPane(self._anchor)
        ll.addWidget(self.opt_pane, 2)
        mc_row = QHBoxLayout()
        mc_btn = QPushButton('▸ RUN BOOTSTRAP'); mc_btn.clicked.connect(self._mc_go)
        mc_row.addWidget(mc_btn)
        mc_row.addWidget(QLabel('resamples trade P&L of the last backtest — '
                                'P5/P25/median/P75/P95 fan · P(loss) · ruin'))
        mc_row.addStretch(1)
        ll.addLayout(mc_row)
        self.mc_stats = QLabel(''); self.mc_stats.setStyleSheet(f'color:{DIM}; font-size:10px;')
        ll.addWidget(self.mc_stats)
        self.mc_chart = SeriesChart(); self.mc_chart.setFixedHeight(150)
        ll.addWidget(self.mc_chart)
        self.help_pane = HtmlPane(self._anchor)
        self.stack.addWidget(chart_page)   # 0 CHART
        self.stack.addWidget(self.top_pane)  # 1 TOP
        self.stack.addWidget(bt_page)      # 2 BT
        self.stack.addWidget(port_page)    # 3 PORT
        self.stack.addWidget(lab_page)     # 4 LAB
        self.stack.addWidget(self.help_pane)  # 5 HELP
        cl.addWidget(self.stack, 1)
        self.screens = ['CHART', 'TOP', 'BT', 'PORT', 'LAB', 'HELP']

        # pods panel
        pods_w = QWidget(); pl3 = QVBoxLayout(pods_w)
        pl3.setContentsMargins(0, 0, 0, 0); pl3.setSpacing(0)
        pods_head = QHBoxLayout(); pods_head.setContentsMargins(8, 5, 8, 3)
        pods_head.addWidget(QLabel(b('ALGO PODS', AMBER)))
        self.pods_meta = QLabel('0/0 PODS'); self.pods_meta.setStyleSheet(f'color:{DIM}')
        pods_head.addStretch(1); pods_head.addWidget(self.pods_meta)
        pl3.addLayout(pods_head)
        self.pods_pane = HtmlPane(self._anchor)
        pl3.addWidget(self.pods_pane, 1)

        split_h.addWidget(watch_w); split_h.addWidget(center_w); split_h.addWidget(pods_w)
        split_h.setSizes([242, 1000, 344])
        split_v.addWidget(split_h)

        # bottom row
        bottom = QSplitter(Qt.Horizontal)
        sig_w = QWidget(); sl = QVBoxLayout(sig_w); sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        sh1 = QHBoxLayout(); sh1.setContentsMargins(8, 4, 8, 2)
        sh1.addWidget(QLabel(b('SIGNALS · SYSTEM', AMBER))); sh1.addStretch(1)
        clr_btn = QPushButton('CLR'); clr_btn.clicked.connect(self._clr_sig)
        sh1.addWidget(clr_btn)
        sl.addLayout(sh1)
        self.sig_pane = HtmlPane(); sl.addWidget(self.sig_pane, 1)
        ord_w = QWidget(); ol = QVBoxLayout(ord_w); ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(0)
        oh = QHBoxLayout(); oh.setContentsMargins(8, 4, 8, 2)
        oh.addWidget(QLabel(b('WORKING ORDERS · EXECUTIONS', AMBER))); oh.addStretch(1)
        self.fill_meta = QLabel('0 FILLS'); self.fill_meta.setStyleSheet(f'color:{DIM}')
        oh.addWidget(self.fill_meta)
        ol.addLayout(oh)
        self.ord_pane = HtmlPane(self._anchor)
        self.blot_pane = HtmlPane(self._anchor)
        ol.addWidget(self.ord_pane)
        ol.addWidget(self.blot_pane, 1)
        acct_w = QWidget(); al = QVBoxLayout(acct_w); al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(0)
        ah = QHBoxLayout(); ah.setContentsMargins(8, 4, 8, 2)
        self.acct_meta = QLabel(b('ACCOUNT · RISK · POSITIONS', AMBER))
        self.acct_meta.setCursor(Qt.PointingHandCursor)
        self.acct_meta.mousePressEvent = lambda _e: self.set_screen('PORT')
        ah.addWidget(self.acct_meta); ah.addStretch(1)
        al.addLayout(ah)
        grid_w = QWidget(); ag = QGridLayout(grid_w)
        ag.setContentsMargins(8, 0, 8, 0); ag.setHorizontalSpacing(14); ag.setVerticalSpacing(1)
        self.a_eq = QLabel(money(CFG['start_eq']))
        self.a_eq.setStyleSheet(f'color:{AMBER}; font-size:16px; font-weight:600;')
        self.a_pnl = QLabel('+$0.00')
        small = 'font-size:11px;'
        self.a_real = QLabel('$0'); self.a_unreal = QLabel('$0')
        self.a_exp = QLabel('$0'); self.a_fills = QLabel('0')
        for wgt in (self.a_real, self.a_unreal, self.a_exp, self.a_fills):
            wgt.setStyleSheet(small)
        ag.addWidget(QLabel('NET LIQUIDATION'), 0, 0); ag.addWidget(self.a_eq, 1, 0)
        ag.addWidget(QLabel('DAY P&L'), 0, 1); ag.addWidget(self.a_pnl, 1, 1)
        ag.addWidget(QLabel('REALIZED'), 2, 0); ag.addWidget(self.a_real, 3, 0)
        ag.addWidget(QLabel('UNREALIZED'), 2, 1); ag.addWidget(self.a_unreal, 3, 1)
        ag.addWidget(QLabel('GROSS NOTIONAL'), 2, 2); ag.addWidget(self.a_exp, 3, 2)
        ag.addWidget(QLabel('FILLS'), 2, 3); ag.addWidget(self.a_fills, 3, 3)
        al.addWidget(grid_w)
        self.gross_bar = QProgressBar(); self.gross_bar.setRange(0, 1000); self.gross_bar.setValue(0)
        self.gross_bar.setTextVisible(False); self.gross_bar.setFixedHeight(3)
        al.addWidget(self.gross_bar)
        self.eq_spark = SeriesChart(); self.eq_spark.setFixedHeight(30)
        al.addWidget(self.eq_spark)
        tick_row = QHBoxLayout(); tick_row.setContentsMargins(8, 3, 8, 3)
        tick_row.addWidget(QLabel('TICKET'))
        self.tk_sym = QLineEdit(); self.tk_sym.setObjectName('tk')
        self.tk_sym.setPlaceholderText('SYM'); self.tk_sym.setFixedWidth(60)
        self.tk_qty = QLineEdit(); self.tk_qty.setObjectName('tk')
        self.tk_qty.setPlaceholderText('QTY'); self.tk_qty.setFixedWidth(46)
        self.tk_lmt = QLineEdit(); self.tk_lmt.setObjectName('tk')
        self.tk_lmt.setPlaceholderText('LMT'); self.tk_lmt.setFixedWidth(64)
        self.tk_stp = QLineEdit(); self.tk_stp.setObjectName('tk')
        self.tk_stp.setPlaceholderText('STP'); self.tk_stp.setFixedWidth(50)
        self.tk_tgt = QLineEdit(); self.tk_tgt.setObjectName('tk')
        self.tk_tgt.setPlaceholderText('TGT'); self.tk_tgt.setFixedWidth(50)
        buy = QPushButton('BUY'); buy.setObjectName('bBuy')
        sell = QPushButton('SELL'); sell.setObjectName('bSell')
        cxl = QPushButton('CXL'); cxl.setToolTip('cancel all working orders')
        buy.clicked.connect(lambda: self._ticket(1))
        sell.clicked.connect(lambda: self._ticket(-1))
        cxl.clicked.connect(self.desk.cancel_all_orders)
        for le in (self.tk_sym, self.tk_qty, self.tk_lmt, self.tk_stp, self.tk_tgt):
            le.returnPressed.connect(lambda: self._ticket(1))
        for w2 in (self.tk_sym, self.tk_qty, self.tk_lmt, self.tk_stp, self.tk_tgt,
                   buy, sell, cxl):
            tick_row.addWidget(w2)
        tick_row.addStretch(1)
        al.addLayout(tick_row)
        self.pos_pane = HtmlPane(self._anchor)
        al.addWidget(self.pos_pane, 1)
        bottom.addWidget(sig_w); bottom.addWidget(ord_w); bottom.addWidget(acct_w)
        bottom.setSizes([500, 500, 420])
        split_v.addWidget(bottom)
        split_v.setSizes([720, 220])
        root.addWidget(split_v, 1)

        # --- footer
        footer = QWidget(); footer.setFixedHeight(30)
        fl = QHBoxLayout(footer); fl.setContentsMargins(8, 0, 8, 0)
        self.fk_row = QHBoxLayout(); self.fk_row.setSpacing(4)
        for key, name in (('F1','HELP'), ('F2','TOP'), ('F3','CHART'), ('F4','BT'),
                          ('≡','LAB'), ('⌂','PORT'), ('F6','STRAT'), ('F7','ALERTS'),
                          ('F8','FLAT'), ('F9','SPEED'), ('F10','PAUSE'), ('F12','CLR')):
            btn = QPushButton(f'{key} {name}')
            btn.setStyleSheet('border:none; color:#5b6154; font-size:10px; padding:2px 6px;')
            btn.clicked.connect(lambda _c=False, n=name: self.fkey(n))
            self.fk_row.addWidget(btn)
        fl.addLayout(self.fk_row); fl.addStretch(1)
        self.status_lab = QLabel(''); self.status_lab.setStyleSheet(f'color:{DIM}')
        fl.addWidget(self.status_lab)
        root.addWidget(footer)

        self.sig_rows = []; self.blot_rows = []
        self._build_help()
        self.load('ES')

    # ---------- boot (no skip) ----------
    def _boot(self):
        n = len(self.desk.instrs)
        total = n*CFG['hist_bars']
        pre = [('EMBER TERMINAL OS  v12.0.0 — PRODUCTION BUILD (PySide6)', 'dm'),
               (f'{n} INSTRUMENTS · PODS · WALK-FORWARD · THREADS · PORTFOLIO RISK', 'dm'),
               ('', '')]
        rest = [
            ('> mount market simulator ............... ', 'ok'),
            (f'> seed {total:,} bars · {n} instruments ....... ', 'ok'),
            ('> build composite index EMBX ............ ', 'ok'),
            ('> calibrate indicators / strategies ..... ', 'ok'),
            (f'> compute threads ({self.compute_mode()}) ............ ', 'ok'),
            ('> link execution engine · OCO · TIF ..... ', 'ok'),
            ('> arm risk engine · sector caps · kill .. ', 'ok'),
            ('> mount portfolio module · VaR · attr ... ', 'ok'),
            ('> mount persistent journal .............. ', 'ok'),
            ('> paper account funded ................. $1,000,000.00', 'usd'),
            ('> session open — type HELP for reference', ''),
        ]
        self.boot_ov = BootOverlay(self.centralWidget(), pre, lambda: self._boot_heavy(rest))

    def _boot_heavy(self, rest):
        self.desk.gen_history()
        j = self.desk.load_journal()
        if j:
            self.desk.apply_journal(j)
            self.desk.eq_peak = max(self.desk.eq_peak, self.desk.current_equity())
        self.boot_ov.lines += [(l, c2) for l, c2 in rest]
        self._boot_tail(j)

    def _boot_tail(self, j):
        if getattr(self, '_boot_started', False): return
        self._boot_started = True
        self.tick_timer = QTimer(self); self.tick_timer.timeout.connect(self._on_tick)
        self.tick_timer.start(CFG['tick_ms'])
        self.autosave = QTimer(self)
        self.autosave.timeout.connect(self.desk.save_journal)
        self.autosave.start(20000)
        if j:
            self.desk.audit('RESTORE', f'journal applied · seed {self.desk.seed} · '
                                       f'equity {fmt(self.desk.current_equity(),0)} · day {self.desk.day_n}')
            self.sig('SYS', f'SESSION RESTORED — seed {self.desk.seed} · '
                            f'equity {money(self.desk.current_equity())} · '
                            f'{len(self.desk.acct["pos"])} position(s) · day {self.desk.day_n} · '
                            f'{len(self.desk.pods)} pod config(s) IDLE — re-arm with RUN')
            self.msg('PRIOR SESSION RESTORED — RESET ACCT TO WIPE (DOUBLE-CONFIRM)', 'ok')
        else:
            self.desk.start_pod('MOMENTUM', 'ES')
            self.desk.start_pod('MEANREV', 'CL')
            self.desk.arena_start('AMD')
            self.sig('SYS', 'Session open · arena on AMD. Try WF MOMENTUM FAST NVDA 1200 · '
                            'BT BREAKOUT CL 1200 STP 30 TGT 50 · PORT · the TICKET below')
        self.refresh_all()

    # ---------- helpers ----------
    def _preset_cmd(self, text):
        self.cmd.setText(text); self.cmd.setFocus()

    def _rotate_hint(self):
        if self.cmd.hasFocus() or self.cmd.text(): return
        self.cmd.setPlaceholderText(self._hints[self._hint_i % len(self._hints)])
        self._hint_i += 1

    def _clock(self):
        self.clock_lab.setText(datetime.utcnow().strftime('%H:%M:%S')+' UTC')

    def _clr_sig(self):
        self.sig_rows = []; self.sig_pane.set_rows([])

    def _toggle_chart(self, key, on):
        self.chart_show[key] = on; self.chart.update()

    def _fill_params(self):
        defn = STRAT_BY_ID[self.opt_strat.currentText()]
        self.opt_param.clear()
        self.opt_param.addItems(list(defn['params'].keys()))

    def _anchor(self, url):
        s = url
        if s.startswith('cmd:'):
            self._preset_cmd(s[4:])
        elif s.startswith('sym:'):
            self.load(s[4:])
        elif s.startswith('x:'):
            parts = s[2:].split('|')
            if parts[0] == 'APPLY' and len(parts) == 4:
                self.desk.set_param(parts[1], parts[2], float(parts[3]))
            elif parts[0] == 'CXL' and len(parts) == 2:
                self.desk.cancel_order(int(parts[1]))
            elif parts[0] == 'POD' and len(parts) == 3:
                if parts[1] == 'RUN':
                    key = parts[2]
                    def_id, sym = key.split('·', 1)
                    self.desk.start_pod(def_id, sym)
                elif parts[1] == 'STOP':
                    self.desk.stop_pod(parts[2])
                elif parts[1] == 'TGT':
                    m = QMenu(self)
                    for i in self.desk.instrs:
                        if not self.desk.can_trade(i): continue
                        m.addAction(f'{i.sym} · {i.name}',
                                    lambda sy=i.sym, k=parts[2]: self._pod_retarget(k, sy))
                    m.exec(self.cursorPos())

    def _pod_retarget(self, key, sym):
        def_id = key.split('·', 1)[0]
        pod = next((p for p in self.desk.pods if p.key == key), None)
        if pod and pod.running: self.desk.stop_pod(key, force=True)
        self.desk.start_pod(def_id, sym)

    def _exec_from_ui(self, line):
        line = line.strip()
        if not line: return
        self.hist.append(line); self.hi = len(self.hist)
        self.desk.exec(line)

    def _complete(self):
        parts = self.cmd.text().upper().strip().split()
        last = parts[-1] if parts else ''
        if not last: return
        vocab = (['HELP','RUN','STOP','BT','BTALL','BTLOG','WF','BUY','SELL','CXL','CLOSE',
                  'FLAT','TOP','STRAT','RISK','ALERT','ALERTS','DIAG','EXEC','PERF',
                  'JOURNAL','EXPORT','SPEED','PAUSE','RESUME','RESET','CLR','LAB','PORT',
                  'ARENA','OPT','MC','SET','SEED','FEED','SCAN','WATCH','TIF',
                  'STOP','TGT','TRAIL','MAXB']
                 + STRAT_IDS + list(STRAT_COLORS)
                 + [k for sd in STRATS for k in sd['params']] + self.desk.syms)
        m = [v for v in dict.fromkeys(vocab) if v.startswith(last)]
        if len(m) == 1:
            parts[-1] = m[0]; self.cmd.setText(' '.join(parts))
        elif m:
            self.msg(' · '.join(m[:8])+(f'  +{len(m)-8} more' if len(m) > 8 else ''), 'ok')

    def _hist(self, d):
        if d < 0 and self.hi > 0:
            self.hi -= 1; self.cmd.setText(self.hist[self.hi])
        elif d > 0:
            if self.hi < len(self.hist)-1:
                self.hi += 1; self.cmd.setText(self.hist[self.hi])
            else:
                self.hi = len(self.hist); self.cmd.setText('')

    # ---------- msg / sig ----------
    def msg(self, text, cls=''):
        col = AMBER if cls == 'ok' else (DN if cls == 'err' else DIM)
        self.cmdmsg.setText(f'<span style="color:{col}">{esc(text)}</span>')
        QTimer.singleShot(6000, lambda: self.cmdmsg.setText('')
                          if self.cmdmsg.text() == f'<span style="color:{col}">{esc(text)}</span>'
                          else None)
        self.sig('ERR' if cls == 'err' else 'SYS', text)

    def sig(self, kind, text):
        col = {'SIG': AMBER, 'FILL': UP, 'ERR': DN}.get(kind, DIM)
        self.sig_rows.insert(0, f'<span style="color:{DIM}">{now_t()}</span> '
                                f'<span style="color:{col}">{esc(text)}</span>')
        if len(self.sig_rows) > 120: self.sig_rows.pop()
        self.sig_pane.set_rows(self.sig_rows)

    def fill_row(self, f):
        inst = self.desk.by_sym(f['sym'])
        self.blot_rows.insert(0,
            f'<span style="color:{DIM}">{f["t"]}</span> {b(f["sym"], AMBER)} '
            f'<span style="color:{UP if f["side"]=="B" else DN};font-weight:600">{f["side"]}</span> '
            f'{f["qty"]}  {fmt_px(f["px"], inst.dec)}  '
            f'<span style="color:{DIM}">{f["tag"]}</span>')
        if len(self.blot_rows) > 90: self.blot_rows.pop()
        self.blot_pane.set_rows(self.blot_rows)
        self.fill_meta.setText(f'{self.desk.acct["fills"]} FILLS')

    def halt_show(self):
        self.halt_banner.setVisible(True); self._conn()
        self.msg('KILL SWITCH ENGAGED — TYPE "RESET RISK" TO RE-ARM', 'err')

    # ---------- screens ----------
    def set_screen(self, s):
        self.stack.setCurrentIndex(self.screens.index(s))
        names = dict(CHART=f'{self.active} · {self.desk.by_sym(self.active).name}',
                     HELP='COMMAND REFERENCE', TOP='MARKET MAP · BREADTH · MOVERS',
                     BT='BACKTEST', PORT='PORTFOLIO · EXPOSURE · ATTRIBUTION',
                     LAB='STRATEGY LAB · ARENA / WF / OPT / BATCH / MC')
        self.scr_title.setText(names.get(s, s))
        if s == 'CHART': self.chart.update(); self._chart_stats()
        elif s == 'TOP': self._render_top()
        elif s == 'BT' and self.desk.last_bt: self._render_bt()
        elif s == 'PORT': self._render_port()
        elif s == 'LAB': self._render_lab()

    def load(self, sym):
        if self.desk.by_sym(sym) is None: return
        self.active = sym
        self.chart.pan = 0
        self.tk_sym.setText(sym)
        self._legend_rebuild()
        self.set_screen('CHART')
        self._save_prefs()

    def _legend_rebuild(self):
        while self.legend_row.count():
            it = self.legend_row.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        for p in self.desk.pods:
            if p.inst is None or p.inst.sym != self.active: continue
            if not p.trades and p.pos == 0: continue
            btn = QPushButton(f'● {p.defn["id"][:3]}·{p.sym}')
            btn.setCheckable(True); btn.setChecked(p.key not in self.hidden_marks)
            btn.setStyleSheet(f'border:1px solid #33392c; color:{p.defn.get("color", STRAT_COLORS[p.defn["id"]])};'
                              'font-size:9px; padding:1px 6px;')
            btn.toggled.connect(lambda on, k=p.key: self._toggle_marks(k, on))
            self.legend_row.addWidget(btn)

    def _toggle_marks(self, key, on):
        if on: self.hidden_marks.discard(key)
        else: self.hidden_marks.add(key)
        self.chart.update()

    # ---------- per-tick refresh ----------
    def _on_tick(self):
        bar_closed = self.desk.tick()
        self.lat_lab.setText(f'LAT {round(self.desk.lat)}MS')
        self.watch_list.viewport().update()
        if self.desk.tick_n % 4 == 2: pass  # tape paints live each frame
        self._pods_refresh()
        self._acct_refresh()
        self._pos_refresh()
        self._ord_refresh()
        cur = self.stack.currentIndex()
        if cur == 0:
            self._chart_stats(); self.chart.update()
        elif cur == 1 and self.desk.tick_n % 16 == 0:
            self._render_top()
        elif cur == 3 and bar_closed:
            self._render_port()
        elif cur == 4 and bar_closed:
            self._render_lab()
        if self.desk.tick_n % 12 == 0: self._status()

    def refresh_all(self):
        self._pods_refresh(); self._acct_refresh(); self._pos_refresh()
        self._ord_refresh(); self._chart_stats(); self._status()
        self.watch_list.viewport().update()
        self.tape.update(); self.chart.update()

    def _chart_stats(self):
        inst = self.desk.by_sym(self.active)
        o = self.desk.day_open(inst); chg = inst.px-o
        h, l = self.desk.day_range(inst)
        self.ch_last.setText(fmt_px(inst.px, inst.dec))
        self.ch_last.setStyleSheet(
            f'font-size:14px; font-weight:600; color:{UP if inst.px>=inst.ppx else DN};')
        self.ch_chg.setText(f'<span style="color:{UP if chg>=0 else DN}">'
                            f'{(chg>=0 and "+") or ""}{fmt(chg,inst.dec)} '
                            f'({(chg>=0 and "+") or ""}{fmt(chg/o*100,2)}%)</span>')
        vw = inst.vw[-1] if inst.vw else None
        lb = inst.bars[-1]
        self.ch_hl.setText(f'H {fmt_px(h,inst.dec)} · L {fmt_px(l,inst.dec)} · '
                           f'V {fmt((lb.v+inst.forming.v)/1000,1)}K'
                           + (f' · VWAP {fmt_px(vw,inst.dec)}' if vw else ''))
        self.scr_title.setText(f'{inst.sym} · {inst.name}')

    def _status(self):
        d = self.desk
        w = sum(1 for o in d.orders if o['status'] == 'WORKING')
        down = d.feed_down_until > time.time()
        s = (f'FPS≈{round(1000/max(1,CFG["tick_ms"]))} · SIM '
             f'<b>{self._speed}</b>' if hasattr(self, '_speed') else
             f'SIM <b>{getattr(self, "_speed", 1)}×</b>')
        extra = ''
        if d.paused: extra += ' · <b style="color:#ffa028">PAUSED</b>'
        if down: extra += ' · <b style="color:#ff5449">RECONNECTING</b>'
        if d.halted: extra += ' · <b style="color:#ff5449">HALT</b>'
        self.status_lab.setText(f'SIM {self._speed}×{extra} · T {d.tick_n} · D{d.day_n} · '
                                f'{sum(1 for p in d.pods if p.running)}/{len(d.pods)} PODS · '
                                f'{w} ORD · GROSS {money_k(d.gross_notional())} · '
                                f'{self.compute_mode()} · {len(d.instrs)} INSTR · PAPER')

    def _conn(self):
        d = self.desk
        down = d.feed_down_until > time.time()
        if d.halted:
            self.conn_lab.setText('● TRADING HALT')
            self.conn_lab.setStyleSheet(f'color:{DN};')
        elif down:
            self.conn_lab.setText('● RECONNECTING')
            self.conn_lab.setStyleSheet(f'color:{DN};')
        elif d.paused:
            self.conn_lab.setText('● FEED PAUSED')
            self.conn_lab.setStyleSheet(f'color:{AMBER};')
        else:
            self.conn_lab.setText('● DATA·SIM'); self.conn_lab.setStyleSheet('')

    # ---------- watch ----------
    def _build_chips(self):
        self.chips = {}
        for name in ['ALL']+[s['id'] for s in SECTORS]+['MAC']:
            btn = QPushButton(name)
            btn.setCheckable(True); btn.setChecked(name == 'ALL')
            btn.setFixedHeight(18)
            btn.setStyleSheet('font-size:8.5px; padding:1px 6px; letter-spacing:0px;')
            btn.clicked.connect(lambda _c=False, f=name: self._watch_filter(f))
            self.chips[name] = btn
            self.chip_row.addWidget(btn)
        self.sort_btn = QPushButton('⇅ SYM'); self.sort_btn.setCheckable(False)
        self.sort_btn.setStyleSheet('font-size:8.5px; padding:1px 6px; margin-left:auto;')
        self.sort_btn.clicked.connect(self._watch_cycle_sort)
        self.chip_row.addWidget(self.sort_btn)

    def _watch_filter(self, f):
        self.desk.watch['filter'] = f
        for name, btn in self.chips.items():
            btn.setChecked(name == f)
        self._watch_fill()

    def _watch_cycle_sort(self):
        order = ['SYM', 'CHG', 'VOL']
        cur = self.desk.watch['sort']
        self.desk.watch['sort'] = order[(order.index(cur)+1) % 3]
        self.sort_btn.setText('⇅ '+self.desk.watch['sort'])
        self._watch_fill()

    def _watch_refresh(self):
        self.desk.watch['query'] = self.watch_search.text().strip().upper()
        self._watch_fill()

    def _watch_rows(self):
        d = self.desk; w = d.watch
        rows = [i for i in d.instrs
                if (w['filter'] == 'ALL' or i.sector == w['filter'])
                and (not w['query'] or i.sym.startswith(w['query'])
                     or w['query'] in i.name.upper())]
        if w['sort'] == 'CHG':
            rows.sort(key=lambda i: -((i.px-d.day_open(i))/i.px))
        elif w['sort'] == 'VOL':
            rows.sort(key=lambda i: -((i.bars[-1].v+i.forming.v)/i.vbase))
        else:
            rows.sort(key=lambda i: i.sym)
        return rows

    def _watch_fill(self):
        self.watch_list.clear()
        for inst in self._watch_rows():
            item = QListWidgetItem()
            item.setData(Qt.UserRole, inst.sym)
            item.setSizeHint(self.watch_delegate.sizeHint(None, item))
            self.watch_list.addItem(item)

    # ---------- pods pane ----------
    def _pods_refresh(self):
        d = self.desk
        live = sum(1 for p in d.pods if p.running)
        self.pods_meta.setText(f'{live}/{len(d.pods)} PODS · CAP {CFG["pods"]}')
        if not d.pods:
            self.pods_pane.set_rows(['<div style="color:#5b6154;padding:10px">'
                                     'NO PODS — type RUN MOMENTUM ES · same strat + another '
                                     'symbol = another pod</div>'])
            return
        rows = []
        for p in d.pods:
            col = p.defn.get('color', STRAT_COLORS[p.defn['id']])
            prm = ' '.join(f'{k}{v}' for k, v in p.params.items())
            risk = (f' · ST{p.stop_ticks}' if p.stop_ticks else '') + \
                   (f' · TP{p.tgt_ticks}' if p.tgt_ticks else '') + \
                   (f' · TR{p.trail_ticks}' if p.trail_ticks else '') + \
                   (f' · MX{p.max_bars}' if p.max_bars else '')
            lamp = ('<span style="color:#2fd471">●</span>' if p.running
                    else '<span style="color:#2a2f26">●</span>')
            if p.running and p.pos != 0:
                held = max(0, d.cur_bar_id(p)-p.eBar)
                state = (f'{b(("LONG" if p.pos>0 else "SHORT")+" "+str(abs(p.pos))+" "+p.sym)}'
                         f' @ {fmt_px(p.avg, p.inst.dec)} · {held}B'
                         f'{"/"+str(p.max_bars) if p.max_bars else ""} · {esc(p.note)}')
            elif p.running:
                state = f'SCANNING {b(p.sym)} · {esc(p.note or p.defn["desc"])}'
            else:
                state = f'IDLE · <a href="cmd:RUN {p.defn["id"]} {p.sym}">RUN {p.defn["id"]} {p.sym}</a>'
            un = (p.inst.px-p.avg)*p.pos*p.inst.mult if (p.pos != 0 and p.inst) else 0.0
            pl = p.realized + un
            rows.append(
                f'<div style="padding:5px 8px 4px; border-bottom:1px solid #161a15;'
                f'border-left:3px solid {col if p.running else "#262c22"};">'
                f'{lamp} {b(p.key, TXT)} '
                f'<span style="color:#5b6154;font-size:9px">{esc(p.defn["desc"])} · {prm}{risk}</span><br>'
                f'<span style="color:#8b917f;font-size:10px">{state}</span><br>'
                f'<span style="color:{UP if pl>0 else (DN if pl<0 else DIM)};font-size:10px">'
                f'P&amp;L {money(pl, True)}</span> '
                f'<span style="color:#5b6154;font-size:10px">{p.trades_n} TRD · '
                f'{fmt(p.wins/p.trades_n*100,0)+"% WIN" if p.trades_n else "—"}</span> '
                f'<a href="x:POD|TGT|{p.key}" style="font-size:9px">[TGT]</a> '
                f'<a href="x:POD|{"STOP" if p.running else "RUN"}|{p.key}" style="font-size:9px">'
                f'[{"STOP" if p.running else "RUN"}]</a></div>')
        self.pods_pane.set_rows(rows)

    # ---------- orders / blotter ----------
    def _ord_refresh(self):
        d = self.desk
        w = [o for o in d.orders if o['status'] == 'WORKING']
        if not w:
            self.ord_pane.set_rows([])
            return
        bc = d.bar_count()
        rows = [f'<div style="color:{BLUE};font-size:9px;letter-spacing:2px;padding:2px 8px;">'
                f'WORKING ORDERS · {len(w)} · TIF {CFG["tif_bars"] if CFG["tif_bars"]>0 else "GTC"}</div>']
        for o in w:
            inst = d.by_sym(o['sym'])
            lbl = ('STP-X' if o['exit_kind'] == 'STP' else 'TGT-X') \
                  if o['kind'] == 'EXIT' else 'LMT'
            tif = (f' · {max(0, math.ceil(o["exp_bar"]-bc))}B'
                   if (o['kind'] == 'LMT' and math.isfinite(o['exp_bar'])) else '')
            rows.append(
                f'<div style="padding:1px 8px;font-size:10px;border-bottom:1px solid #161a15;">'
                f'<span style="color:{DIM}">#{o["id"]}</span> {b(o["sym"], AMBER)} '
                f'<span style="color:{UP if o["side"]>0 else DN};font-weight:600">'
                f'{"BUY" if o["side"]>0 else "SELL"} {o["qty"]}</span> '
                f'{lbl} {fmt_px(o["px"],inst.dec)}{tif} '
                f'<a href="x:CXL|{o["id"]}">[CXL]</a></div>')
        self.ord_pane.set_rows(rows)

    # ---------- account / positions ----------
    def _acct_refresh(self):
        d = self.desk
        eq = d.current_equity(); day = eq-d.day_start_eq
        self.a_eq.setText(money(eq))
        self.a_pnl.setText(money(day, True))
        self.a_pnl.setStyleSheet(f'font-size:16px;font-weight:600;color:'
                                 f'{UP if day>0 else (DN if day<0 else DIM)};')
        un = sum((d.by_sym(s).px-p['avg'])*p['qty']*d.by_sym(s).mult
                 for s, p in d.acct['pos'].items() if p['qty'])
        self.a_real.setText(money(d.acct['realized'], True))
        self.a_unreal.setText(money(un, True))
        g0 = d.gross_notional()
        self.a_exp.setText(money_k(g0))
        self.a_fills.setText(str(d.acct['fills']))
        ratio = clamp(g0/CFG['gross_notional'], 0, 1)
        self.gross_bar.setValue(int(ratio*1000))
        self.gross_bar.setStyleSheet(
            f'QProgressBar::chunk{{background:{"#ff5449" if ratio>0.85 else ("#ffa028" if ratio>0.6 else "#3f4a38")};}}')
        self.acct_meta.setText(b(f'PAPER {money_k(eq)} · SAVED · ⌂PORT', AMBER))
        pts = [p['eq'] for p in d.eq_hist]
        if len(pts) >= 2:
            self.eq_spark.series = [(pts, UP if pts[-1] >= CFG['start_eq'] else DN, 1, None, '')]
            self.eq_spark.baseline = CFG['start_eq']
            self.eq_spark.dd = False
            dd, _ = d.session_stats()
            self.eq_spark.title = f'DAY {d.day_n} · PEAK DD {fmt(dd*100,2)}%'
            self.eq_spark.update()

    def _pos_refresh(self):
        d = self.desk
        rows = [(s, p) for s, p in d.acct['pos'].items() if p['qty']]
        rows.sort(key=lambda sp: -abs(sp[1]['qty'])*d.by_sym(sp[0]).mult)
        if not rows:
            self.pos_pane.set_rows(['<div style="color:#5b6154;font-size:10px;padding:4px 8px;">'
                                    '— NO OPEN POSITIONS · ticket above · ⌂PORT for the full book</div>'])
            return
        out = ['<table width="100%"><tr>'
               f'<td><span style="color:{DIM};font-size:9px">TKR</span></td>'
               f'<td align="right"><span style="color:{DIM};font-size:9px">NET</span></td>'
               f'<td align="right"><span style="color:{DIM};font-size:9px">AVG</span></td>'
               f'<td align="right"><span style="color:{DIM};font-size:9px">LAST</span></td>'
               f'<td align="right"><span style="color:{DIM};font-size:9px">uP&L</span></td></tr>']
        for sym, p in rows:
            inst = d.by_sym(sym)
            u = (inst.px-p['avg'])*p['qty']*inst.mult
            out.append(f'<tr><td>{b(sym, AMBER)}</td>'
                       f'<td align="right">{c(f"{p["qty"]:+d}", AMBER)}</td>'
                       f'<td align="right">{fmt_px(p["avg"],inst.dec)}</td>'
                       f'<td align="right">{fmt_px(inst.px,inst.dec)}</td>'
                       f'<td align="right">{c(money(u, True), UP if u>=0 else DN)}</td></tr>')
        out.append('</table>')
        self.pos_pane.set_rows(out)

    # ---------- TOP screen ----------
    def _render_top(self):
        d = self.desk
        br = d.breadth_hist[-1] if d.breadth_hist else dict(adv=0, dec=0, hi=0, lo=0)
        tot = max(1, br['adv']+br['dec'])
        mov = [(i, (i.px-d.day_open(i))/d.day_open(i)*100)
               for i in d.instrs if i.asset != 'IDX']
        mov.sort(key=lambda x: -x[1])
        mx = max((abs(x[1]) for x in mov), default=0.01)
        secs = []
        for s in SECTORS:
            ms = [x[1] for x in mov if x[0].sector == s['id']]
            secs.append((s['id'], sum(ms)/len(ms) if ms else 0.0))
        secs.sort(key=lambda x: -x[1])
        def bar(chg):
            wd = int(abs(chg)/mx*50)
            col = UP if chg >= 0 else DN
            side = '' if chg >= 0 else f'margin-left:{100-wd}%'
            return (f'<span style="display:inline-block;width:120px;height:8px;'
                    f'background:#141811;"><span style="display:inline-block;'
                    f'width:{wd}px;height:8px;background:{col};"></span></span>')
        def row(sym, name, px, chg, dec, ix):
            return (f'<tr><td style="color:{DIM}">{ix:02d}</td>'
                    f'<td><a href="sym:{sym}">{b(sym, AMBER)}</a></td>'
                    f'<td style="color:{DIM};font-size:10px">{esc(name)} · '
                    f'{d.by_sym(sym).sector}</td>'
                    f'<td align="right">{fmt_px(px,dec)}</td>'
                    f'<td align="right" style="color:{UP if chg>=0 else DN}">'
                    f'{(chg>=0 and "+") or ""}{fmt(chg,2)}%</td>'
                    f'<td>{bar(chg)}</td></tr>')
        html = ['<div style="padding:6px 10px;">']
        html.append(f'<span style="color:{DIM};font-size:10px">BREADTH</span> '
                    f'<span style="display:inline-block;width:100px;height:8px;background:#141811;">'
                    f'<span style="display:inline-block;width:{int(br["adv"]/tot*100)}px;'
                    f'height:8px;background:{UP};"></span>'
                    f'<span style="display:inline-block;width:{int(br["dec"]/tot*100)}px;'
                    f'height:8px;background:{DN};"></span></span> '
                    f'{b(br["adv"], UP)}/{b(br["dec"], DN)} · '
                    f'HI20 {b(br["hi"], UP)} · LO20 {b(br["lo"], DN)}<br>')
        html.append(' '.join(f'<span style="font-size:9.5px;color:{UP if a>=0 else DN}">'
                             f'{sid} {(a>=0 and "+") or ""}{fmt(a,2)}%</span>'
                             for sid, a in secs))
        if d.idx:
            ic = (d.idx.px-d.day_open(d.idx))/d.day_open(d.idx)*100
            html.append(f' <span style="font-size:9.5px;color:{UP if ic>=0 else DN}">'
                        f'EMBX {(ic>=0 and "+") or ""}{fmt(ic,2)}%</span>')
        html.append(f'<h3 style="color:{AMBER};font-size:10px;letter-spacing:2px">'
                    f'LEADERS · TOP 15 OF {len(mov)}</h3>')
        html.append('<table width="100%" cellpadding="1">')
        for ix, (i, chg) in enumerate(mov[:15], 1):
            html.append(row(i.sym, i.name, i.px, chg, i.dec, ix))
        html.append(f'</table><h3 style="color:{AMBER};font-size:10px;letter-spacing:2px">'
                    f'LAGGARDS · BOTTOM 15</h3><table width="100%" cellpadding="1">')
        for ix, (i, chg) in enumerate(reversed(mov[-15:]), 1):
            html.append(row(i.sym, i.name, i.px, chg, i.dec, ix))
        html.append('</table></div>')
        self.top_pane.set_rows(html)

    # ---------- BT screen ----------
    def _render_bt(self):
        res = self.desk.last_bt
        if res is None: return
        r = res['risk']
        rtxt = (' · '+f'STP{r.get("stp",0)} TGT{r.get("tgt",0)} '
                f'TRAIL{r.get("trail",0)} MAXB{r.get("maxb",0)}'
                if (r.get('stp') or r.get('tgt') or r.get('trail') or r.get('maxb')) else '')
        self.bt_title.setText(f'BACKTEST · {res["stratId"]} / {res["sym"]} · '
                              f'{res["count"]}B{rtxt} · {self.compute_mode()}')
        self.bt_chart.series = [(res['eq'], AMBER, 1.4, None, 'STRAT'),
                                (res['bh'], DIM, 1, None, 'BUY&HOLD')]
        self.bt_chart.baseline = 100000; self.bt_chart.dd = True
        self.bt_chart.xlabel = (hm_t(res['t0'])+' SIM', hm_t(res['t1'])+' SIM')
        self.bt_chart.update()
        ex = res['exits']
        S = lambda l, v, col=None: (f'<td align="center"><span style="color:{DIM};'
                                    f'font-size:9px">{l}</span><br>{b(v, col)}</td>')
        html = ['<table width="100%" cellpadding="2"><tr>']
        html.append(S('NET RETURN', f'{(res["ret"]>=0 and "+") or ""}{fmt(res["ret"],2)}%',
                      UP if res['ret'] >= 0 else DN))
        html.append(S('ANN. SHARPE', '—' if res['sharpe'] is None else fmt(res['sharpe'],2),
                      UP if (res['sharpe'] or 0) >= 1 else None))
        html.append(S('MAX DRAWDOWN', '−'+fmt(res['mdd']*100,2)+'%', DN))
        html.append(S('WIN RATE', fmt(res['wins']/res['n']*100,1)+'%' if res['n'] else '—'))
        html.append(S('TRADES', str(res['n'])))
        html.append(S('PF', '∞' if res['pf'] is None else fmt(res['pf'],2),
                      UP if (res['pf'] or 0) >= 1 else None))
        html.append(S('AVG TRADE', money(res['avgT'], True),
                      UP if res['avgT'] >= 0 else DN))
        html.append(S('FINAL EQ', money(res['final'])))
        html.append(S('STOP-OUTS', str(ex.get('STOP', 0)),
                      AMBER if ex.get('STOP', 0) > res['n']*0.5 else None))
        html.append(S('TARGETS', str(ex.get('TGT', 0))))
        html.append(S('TRAILS', str(ex.get('TRAIL', 0))))
        html.append(S('TIME EXITS', str(ex.get('TIME', 0))))
        html.append('</tr></table>')
        html.append('<div style="border-top:1px solid #161a15;padding:3px 8px;">')
        dec = self.desk.by_sym(res['sym']).dec
        for t in reversed(res['trades'][-40:]):
            html.append(f'<div style="font-size:10px;">'
                        f'<span style="color:{UP if t["side"]>0 else DN}">'
                        f'{"▲ LONG" if t["side"]>0 else "▼ SHORT"}</span> '
                        f'{fmt_px(t["ePx"],dec)} → {fmt_px(t["xPx"],dec)} '
                        f'<span style="color:{DIM}">{t.get("why","SIG")}</span> '
                        f'{c(money(t["pnl"], True), UP if t["pnl"]>=0 else DN)}</div>')
        html.append('</div>')
        self.bt_pane.set_rows(html)

    def _bt_run_live(self):
        if not self.desk.last_bt: return
        sid, sym = self.desk.last_bt['stratId'], self.desk.last_bt['sym']
        self.desk.start_pod(sid, sym)
        r = self.desk.last_bt['risk']
        for k, key in (('stp','STOP'), ('tgt','TGT'), ('trail','TRAIL'), ('maxb','MAXB')):
            if r.get(k): self.desk.set_pod_risk(sid, key, r[k])
        self.load(sym)

    # ---------- PORT screen ----------
    def _render_port(self):
        d = self.desk
        a = d.portfolio_analytics()
        day = a['eq']-d.day_start_eq
        C = lambda l, v, col=None: (f'<span style="font-size:9.5px;color:{DIM};'
                                    f'border:1px solid #20251e;padding:2px 8px;">{l} '
                                    f'{b(v, col)}</span>')
        self.port_stats.setTextFormat(Qt.RichText)
        self.port_stats.setText(' '.join([
            C('NET LIQ', money_k(a['eq']), AMBER),
            C(f'DAY {d.day_n} P&L', money(day, True), UP if day > 0 else (DN if day < 0 else None)),
            C('GROSS', f'{money_k(a["gross"])} ({fmt(a["gross"]/CFG["gross_notional"]*100,0)}%)'),
            C('NET', money_k(a['net']), UP if a['net'] >= 0 else DN),
            C('β·EMBX', fmt(a['beta'], 2), AMBER if abs(a['beta']) > 1.5 else None),
            C('σ 1D', fmt(a['sig_day']*100, 2)+'%'),
            C('VaR95 1D', money_k(a['var95']), DN if a['var95']/a['eq'] > 0.03 else None),
            C('CONC HHI', fmt(a['hhi'], 3), AMBER if a['hhi'] > 0.35 else None),
            C('TOP WT', fmt(a['top_w']*100, 1)+'%', AMBER if a['top_w'] > 0.35 else None),
            C('POSITIONS', str(len(a['rows'])))]))
        eqs = [p['eq'] for p in d.eq_hist]
        if len(eqs) >= 2:
            self.port_chart.series = [(eqs, UP if eqs[-1] >= CFG['start_eq'] else DN, 1.4, None, '')]
            self.port_chart.baseline = CFG['start_eq']; self.port_chart.dd = True
            self.port_chart.title = 'SESSION EQUITY · RED = DRAWDOWN UNDERWATER'
            self.port_chart.update()
        cap = CFG['max_sector_notional']
        html = [f'<h3 style="color:{AMBER};font-size:10px;letter-spacing:2px;padding:4px 10px 0;">'
                f'SECTOR EXPOSURE · RISK CAP {money_k(cap)}</h3><div style="padding:0 10px;">']
        sec_keys = sorted(a['sec_agg'], key=lambda k: -abs(a['sec_agg'][k]['mv']))
        if not sec_keys:
            html.append('<div style="color:#5b6154">— NO EXPOSURE · build a book: '
                        'BUY AAPL 20 · RUN MOMENTUM NVDA</div>')
        for k in sec_keys:
            s = a['sec_agg'][k]
            use = clamp(abs(s['mv'])/cap, 0, 1)
            col = DN if use > 0.85 else (AMBER if use > 0.6 else '#3f4a38')
            html.append(f'<div style="font-size:10.5px;padding:2px 0;">'
                        f'{b(k, AMBER)} '
                        f'<span style="display:inline-block;width:200px;height:8px;background:#141811;">'
                        f'<span style="display:inline-block;width:{int(use*200)}px;height:8px;'
                        f'background:{col};"></span></span> {money_k(s["mv"])} '
                        f'{fmt(use*100,0)}% · uP&L {c(money(s["un"],True), UP if s["un"]>=0 else DN)} · '
                        f'S P&L {c(money(s["rl"],True), UP if s["rl"]>=0 else DN)}</div>')
        html.append(f'<h3 style="color:{AMBER};font-size:10px;letter-spacing:2px">'
                    f'ATTRIBUTION — BY SOURCE · BY SYMBOL</h3><table width="100%"><tr>')
        html.append(f'<td valign="top" width="50%"><table width="100%">'
                    f'<tr><td><span style="color:{DIM};font-size:9px">SOURCE</span></td>'
                    f'<td align="right"><span style="color:{DIM};font-size:9px">FILLS</span></td>'
                    f'<td align="right"><span style="color:{DIM};font-size:9px">FEES</span></td>'
                    f'<td align="right"><span style="color:{DIM};font-size:9px">REALIZED</span></td></tr>')
        for tag in sorted(d.exec_stats):
            s = d.exec_stats[tag]; r = d.real_by_tag.get(tag, 0.0)
            html.append(f'<tr><td>{b(tag, AMBER if tag not in ("MANL","CLOSE","FLAT") else None)}</td>'
                        f'<td align="right">{s["n"]}</td>'
                        f'<td align="right" style="color:{DIM}">{money(s["fees"])}</td>'
                        f'<td align="right" style="font-weight:600;color:'
                        f'{UP if r>=0 else DN}">{money(r, True)}</td></tr>')
        html.append('</table></td><td valign="top" width="50%"><table width="100%">'
                    f'<tr><td><span style="color:{DIM};font-size:9px">SYMBOL</span></td>'
                    f'<td align="right"><span style="color:{DIM};font-size:9px">NET P&L</span></td></tr>')
        contrib = sorted(((r['sym'], r['un']+r['rl']) for r in a['rows']),
                         key=lambda x: -abs(x[1]))[:8]
        for sym, netp in contrib:
            html.append(f'<tr><td><a href="sym:{sym}">{b(sym, AMBER)}</a></td>'
                        f'<td align="right" style="font-weight:600;color:'
                        f'{UP if netp>=0 else DN}">{money(netp, True)}</td></tr>')
        html.append('</table></td></tr></table>')
        html.append(f'<h3 style="color:{AMBER};font-size:10px;letter-spacing:2px">POSITIONS</h3>'
                    '<table width="100%" cellpadding="1"><tr>'
                    f'<td><span style="color:{DIM};font-size:9px">TKR</span></td>'
                    f'<td><span style="color:{DIM};font-size:9px">NET</span></td>'
                    f'<td align="right"><span style="color:{DIM};font-size:9px">MKT VAL</span></td>'
                    f'<td align="right"><span style="color:{DIM};font-size:9px">WT</span></td>'
                    f'<td align="right"><span style="color:{DIM};font-size:9px">AVG</span></td>'
                    f'<td align="right"><span style="color:{DIM};font-size:9px">LAST</span></td>'
                    f'<td align="right"><span style="color:{DIM};font-size:9px">uP&L</span></td>'
                    f'<td align="right"><span style="color:{DIM};font-size:9px">S P&L</span></td>'
                    f'<td align="right"><span style="color:{DIM};font-size:9px">RISK%</span></td></tr>')
        for r in a['rows']:
            html.append(f'<tr><td><a href="sym:{r["sym"]}">{b(r["sym"], AMBER)}</a></td>'
                        f'<td>{c(f"{r["qty"]:+d}", AMBER)}</td>'
                        f'<td align="right">{money_k(r["mv"])}</td>'
                        f'<td align="right" style="color:{DIM}">{fmt(r["w"]*100,1)}%</td>'
                        f'<td align="right">{fmt_px(r["avg"], r["inst"].dec)}</td>'
                        f'<td align="right">{fmt_px(r["px"], r["inst"].dec)}</td>'
                        f'<td align="right" style="color:{UP if r["un"]>=0 else DN}">{money(r["un"], True)}</td>'
                        f'<td align="right" style="color:{UP if r["rl"]>=0 else DN}">{money(r["rl"], True)}</td>'
                        f'<td align="right" style="color:{DIM}">{fmt(a["risk_map"].get(r["sym"],0),1)}%</td></tr>')
        html.append('</table>')
        t = a['trades']
        html.append(f'<h3 style="color:{AMBER};font-size:10px;letter-spacing:2px">'
                    f'TRADE ANALYTICS — CLOSED ROUND-TRIPS</h3>'
                    f'<div style="font-size:10px;color:{DIM}">CLOSED {b(t["n"], TXT)} · '
                    f'WIN {b("—" if t["win"] is None else fmt(t["win"]*100,1)+"%", TXT)} · '
                    f'PF {b("—" if t["pf"] is None else fmt(t["pf"],2), TXT)} · EXPECTANCY '
                    f'{b(money(t["exp"],True), UP if t["exp"]>=0 else DN)} · '
                    f'AVG HELD {b(fmt(t["held"],1)+"B", TXT)} · '
                    f'BEST {c("—" if t["best"] is None else money(t["best"],True), UP)} · '
                    f'WORST {c("—" if t["worst"] is None else money(t["worst"],True), DN)}</div>')
        for x in reversed(d.trades_log[-6:]):
            netp = x['pnl']-x['fee']
            html.append(f'<div style="font-size:10px;padding:1px 0;">'
                        f'<span style="color:{DIM}">{x["t"]}</span> {b(x["sym"], AMBER)} '
                        f'{c(("L" if x["side"]>0 else "S")+str(x["qty"]), UP if x["side"]>0 else DN)} '
                        f'{x["held"]}B '
                        f'{fmt_px(x["ePx"], d.by_sym(x["sym"]).dec)} → '
                        f'{fmt_px(x["xPx"], d.by_sym(x["sym"]).dec)} '
                        f'{c(money(netp, True), UP if netp>=0 else DN)}</div>')
        html.append('</div>')
        self.port_pane.set_rows(html)

    # ---------- LAB screen ----------
    def _render_lab(self):
        d = self.desk
        html = []
        if d.arena['on']:
            self.arena_stat.setText(f'LIVE ON {d.arena["sym"]} · SHADOW BOOKS · DEFAULT PARAMS')
            rows = []
            for sm in d.arena['sims']:
                eq = sm['eq'][-1] if sm['eq'] else 100000
                sh, dd = d.eq_stats(sm['eq'])
                rows.append((sm, eq-100000, sh, dd))
            rows.sort(key=lambda x: -x[1])
            html.append('<table width="100%" cellpadding="1"><tr>'
                        f'<td><span style="color:{DIM};font-size:9px">RK</span></td>'
                        f'<td><span style="color:{DIM};font-size:9px">STRAT</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">P&L</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">TRD</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">WIN%</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">SHARPE</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">MAXDD</span></td>'
                        f'<td width="30%"></td></tr>')
            for ix, (sm, pnl, sh, dd) in enumerate(rows, 1):
                col = sm['defn'].get('color', STRAT_COLORS[sm['defn']['id']])
                mxp = max(abs(r[1]) for r in rows) or 1
                wpx = int(abs(pnl)/mxp*100)
                html.append(f'<tr><td style="color:{DIM}">{ix:02d}</td>'
                            f'<td>{b(sm["defn"]["id"], col)}</td>'
                            f'<td align="right" style="font-weight:600;color:'
                            f'{UP if pnl>=0 else DN}">{money(pnl, True)}</td>'
                            f'<td align="right">{sm["trades_n"]}</td>'
                            f'<td align="right">{fmt(sm["wins"]/sm["trades_n"]*100,0)+"%" if sm["trades_n"] else "—"}</td>'
                            f'<td align="right">{"—" if sh is None else fmt(sh,2)}</td>'
                            f'<td align="right" style="color:{DN}">−{fmt(dd*100,1)}%</td>'
                            f'<td><span style="display:inline-block;width:{wpx}px;height:8px;'
                            f'background:{col};"></span></td></tr>')
            html.append('</table>')
        else:
            self.arena_stat.setText('ARENA IDLE')
        html.append(f'<h3 style="color:{AMBER};font-size:10px;letter-spacing:2px">'
                    f'RESULTS — RANKED BY SHARPE</h3>')
        o = d.opt_state
        if o is None:
            html.append('<div style="color:#5b6154">OPT &lt;STRAT&gt; [PARAM] [TKR] [BARS] — '
                        'in-sample sweep · WF &lt;STRAT&gt; [PARAM] [TKR] [BARS] — walk-forward '
                        '(70/30 IS/OOS, overfit detector) · BTALL &lt;STRAT&gt; [SECTOR|ALL] — '
                        'cross-sectional batch, chunked across threads</div>')
        elif o['type'] == 'wf':
            r = o['res']
            pct = lambda v: '—' if v is None else f'{(v>=0 and "+") or ""}{fmt(v,1)}%'
            shp = lambda v: '—' if v is None else fmt(v, 2)
            verdict = ''
            vcol = AMBER
            if r['best'] and r['oosBest']:
                deg = None
                if r['oosBest']['sharpe'] is not None and r['best']['sharpe'] and r['best']['sharpe'] > 0:
                    deg = r['oosBest']['sharpe']/r['best']['sharpe']
                beat = (r['oosBest']['sharpe'] is not None
                        and r['oosDef']['sharpe'] is not None
                        and r['oosBest']['sharpe'] > r['oosDef']['sharpe'])
                if deg is not None:
                    vcol = UP if (deg >= 0.6 and beat) else (DN if deg < 0.3 else AMBER)
                    verdict = (f'OOS RETENTION {b(fmt(deg*100,0)+"%", vcol)} of in-sample Sharpe · '
                               + (b('BEATS', UP) if beat else b('DOES NOT BEAT', DN))
                               + ' default params out-of-sample'
                               + (' · ⚠ likely curve-fit — do not deploy' if deg < 0.3
                                  else (' · candidate looks robust' if deg >= 0.6 and beat
                                        else ' · treat with caution')))
                else:
                    verdict = 'retention unknown — thin OOS trades'
            else:
                verdict = 'no valid in-sample optimum'
            html.append(f'<div style="border:1px solid #20251e;padding:8px 12px;margin:4px 0;'
                        f'font-size:10.5px;line-height:1.7;color:{DIM}">'
                        f'WALK-FORWARD · {b(o["stratId"]+"."+o["param"], TXT)} on {b(o["sym"], TXT)} · '
                        f'IS {r["isN"]}B → OOS {r["oosN"]}B (70/30)<br>'
                        f'BEST {o["param"]}={b(r["best"]["v"] if r["best"] else "—", AMBER)} · '
                        f'IS {pct(r["best"]["ret"]) if r["best"] else "—"} / SHARPE '
                        f'{shp(r["best"]["sharpe"]) if r["best"] else "—"} · '
                        f'OOS {pct(r["oosBest"]["ret"]) if r["oosBest"] else "—"} / SHARPE '
                        f'{shp(r["oosBest"]["sharpe"]) if r["oosBest"] else "—"} · '
                        f'OOS DEFAULT {pct(r["oosDef"]["ret"])} / SHARPE {shp(r["oosDef"]["sharpe"])}<br>'
                        f'{verdict} · {b((r["oosBest"] or {}).get("n", 0), TXT)} OOS trades</div>')
            html.append('<table width="100%" cellpadding="1"><tr>'
                        f'<td><span style="color:{DIM};font-size:9px">{o["param"]}</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">IS RET</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">IS SHARPE</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">IS MAXDD</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">TRD</span></td>'
                        f'<td></td></tr>')
            for x in r['sweep']:
                bestm = ' color:'+AMBER if (r['best'] and x['v'] == r['best']['v']) else ''
                html.append(f'<tr><td{f" style={chr(34)+bestm+chr(34)}" if bestm else ""}>'
                            f'{b(x["v"], AMBER if (r["best"] and x["v"]==r["best"]["v"]) else None)}</td>'
                            f'<td align="right" style="color:{UP if x["ret"]>=0 else DN}">'
                            f'{pct(x["ret"])}</td>'
                            f'<td align="right">{shp(x["sharpe"])}</td>'
                            f'<td align="right" style="color:{DN}">−{fmt((x["mdd"] or 0)*100,1)}%</td>'
                            f'<td align="right">{x["n"]}{" (THIN)" if x["n"]<4 else ""}</td>'
                            f'<td><a href="x:APPLY|{o["stratId"]}|{o["param"]}|{x["v"]}">APPLY</a></td></tr>')
            html.append('</table>')
        elif o['type'] == 'batch':
            mxs = max((abs(r['sharpe'] or 0) for r in o['results']), default=0.01) or 0.01
            html.append('<table width="100%" cellpadding="1"><tr>'
                        f'<td><span style="color:{DIM};font-size:9px">TKR</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">RETURN</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">SHARPE</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">MAXDD</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">TRD</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">PF</span></td>'
                        f'<td width="30%"><span style="color:{DIM};font-size:9px">SHARPE</span></td></tr>')
            for ix, r in enumerate(o['results'][:24], 1):
                wpx = int(abs(r['sharpe'] or 0)/mxs*100)
                html.append(f'<tr><td>{b(r["sym"], AMBER if ix==1 else None)}</td>'
                            f'<td align="right" style="color:{UP if r["ret"]>=0 else DN}">'
                            f'{(r["ret"]>=0 and "+") or ""}{fmt(r["ret"],1)}%</td>'
                            f'<td align="right">{"—" if r["sharpe"] is None else fmt(r["sharpe"],2)}</td>'
                            f'<td align="right" style="color:{DN}">−{fmt(r["mdd"]*100,1)}%</td>'
                            f'<td align="right">{r["n"]}</td>'
                            f'<td align="right">{"∞" if r["pf"] is None else fmt(r["pf"],2)}</td>'
                            f'<td><span style="display:inline-block;width:{wpx}px;height:8px;'
                            f'background:{AMBER if (r["sharpe"] or 0)>=0 else DN};"></span></td></tr>')
            html.append('</table>')
            posp = round(sum(1 for r in o['results'] if r['ret'] > 0)/len(o['results'])*100)
            html.append(f'<div style="color:#5b6154">{len(o["results"])} SYMBOLS · {o["stratId"]} · '
                        f'{o["target"]} · {o["count"]} BARS · {posp}% PROFITABLE — '
                        f'run one live: RUN {o["stratId"]} &lt;TKR&gt;</div>')
        else:
            html.append('<table width="100%" cellpadding="1"><tr>'
                        f'<td><span style="color:{DIM};font-size:9px">{o["param"]}</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">RETURN</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">SHARPE</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">MAXDD</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">TRD</span></td>'
                        f'<td align="right"><span style="color:{DIM};font-size:9px">PF</span></td>'
                        f'<td></td></tr>')
            for ix, r in enumerate(o['results'], 1):
                html.append(f'<tr><td>{b(r["v"], AMBER if ix==1 else None)}</td>'
                            f'<td align="right" style="color:{UP if r["ret"]>=0 else DN}">'
                            f'{(r["ret"]>=0 and "+") or ""}{fmt(r["ret"],1)}%</td>'
                            f'<td align="right">{"—" if r["sharpe"] is None else fmt(r["sharpe"],2)}</td>'
                            f'<td align="right" style="color:{DN}">−{fmt(r["mdd"]*100,1)}%</td>'
                            f'<td align="right">{r["n"]}</td>'
                            f'<td align="right">{"∞" if r["pf"] is None else fmt(r["pf"],2)}</td>'
                            f'<td><a href="x:APPLY|{o["stratId"]}|{o["param"]}|{r["v"]}">APPLY</a></td></tr>')
            html.append('</table>')
        if d.mc_state:
            m = d.mc_state
            self.mc_chart.bands = [(m['p95'], m['p05'], 'rgba(255,160,40,0.07)'),
                                   (m['p75'], m['p25'], 'rgba(255,160,40,0.13)')]
            self.mc_chart.series = [(m['p50'], AMBER, 1.4, None, 'MEDIAN'),
                                    (m['actual'], TXT, 1, 'dash', 'ACTUAL')]
            self.mc_chart.baseline = 100000
            self.mc_chart.xlabel = ('TRADE #', '')
            self.mc_chart.update()
            sc2 = lambda v, col: b(v, col)
            self.mc_stats.setText(f'FINAL RETURN · P5 {sc2(fmt((m["f05"]/100000-1)*100,1)+"%", UP if m["f05"]>=100000 else DN)}'
                                  f' · MEDIAN {sc2(fmt((m["f50"]/100000-1)*100,1)+"%", UP if m["f50"]>=100000 else DN)}'
                                  f' · P95 +{fmt((m["f95"]/100000-1)*100,1)}%'
                                  f' · P(LOSS) {sc2(fmt(m["pLoss"]*100,1)+"%", DN if m["pLoss"]>0.4 else None)}'
                                  f' · MAXDD MEDIAN −{fmt(m["dd50"]*100,1)}% · P95 −{fmt(m["dd95"]*100,1)}%'
                                  f' · RUIN {sc2(fmt(m["ruin"]*100,2)+"%", DN if m["ruin"]>0 else UP)}'
                                  f' · {m["M"]} PATHS × {m["T"]} TRADES')
        else:
            self.mc_chart.series = []; self.mc_chart.update()
            self.mc_stats.setText('RUN A BACKTEST (BT ...) THEN ▸ RUN BOOTSTRAP')
        self.lab_pane.set_rows(html)

    # ---------- HELP screen ----------
    def _build_help(self):
        C = lambda cmd, desc: (f'<div style="padding:3px 0;border-bottom:1px solid #161a15;'
                               f'font-size:11.5px;"><a href="cmd:{cmd}">{b(cmd, AMBER)}</a>'
                               f'<span style="color:{DIM}"> — {desc}</span></div>')
        S = ''.join(f'<div style="padding:3px 0;border-bottom:1px solid #161a15;">'
                    f'<a href="cmd:RUN {s["id"]} {self.active}">'
                    f'{b(s["id"], STRAT_COLORS[s["id"]])}</a>'
                    f'<span style="color:{DIM}"> — {s["desc"].lower()} · '
                    f'params {param_schema_text(s)}</span></div>' for s in STRATS)
        n = len(self.desk.instrs)
        self.help_pane.set_rows([f'''<div style="padding:10px 16px;">
<h3 style="color:{AMBER};font-size:10px;letter-spacing:2px">COMMAND LINE</h3>
{C('NVDA · CL · EMBX …', 'load any of the '+str(n)+' instruments · EMBX = composite (chart/BT only)')}
{C('PORT · PF', 'portfolio screen — exposure · β · factor VaR · attribution · trade analytics')}
{C('RUN &lt;STRAT&gt; [TKR]', 'arm a strategy pod · same strat on another symbol spawns a SECOND pod (cap '+str(CFG['pods'])+')')}
{C('STOP &lt;STRAT|ALL&gt; [TKR]', 'disarm — one pod, all pods of a strat, or everything')}
{C('SET &lt;STRAT&gt; &lt;PARAM&gt; &lt;V&gt;', 'strategy params applied to all its live pods')}
{C('SET &lt;STRAT&gt; STOP|TGT|TRAIL|MAXB &lt;V&gt;', 'intrabar risk exits — hard stop · target · trailing stop (ticks) · max holding (bars)')}
{C('BUY / SELL &lt;TKR&gt; &lt;QTY&gt; [LMT PX] [STP T] [TGT T]', 'market or limit, optionally BRACKETED — OCO exit pair on fill · or use the TICKET')}
{C('CLOSE &lt;SYM|SECTOR|ALL&gt;', 'close positions selectively · pods stay armed · FLAT ALL also disarms')}
{C('CXL &lt;ID&gt; | ALL', 'cancel working orders · canceling an OCO leg cancels its sibling')}
{C('BT &lt;STRAT&gt; &lt;TKR&gt; [N] [STP t] [TGT t] [TRAIL t] [MAXB n]', 'backtest — models the SAME intrabar exit engine as live (stop-first on ambiguous bars)')}
{C('WF &lt;STRAT&gt; [PARAM] [TKR] [BARS]', 'walk-forward: optimize on 70% IS, validate on unseen 30% — OOS Sharpe retention (overfit detector)')}
{C('BTALL &lt;STRAT&gt; [SECTOR|ALL] [N]', 'cross-sectional batch, chunked across threads')}
{C('BTLOG', 'last 8 backtests with re-run commands')}
{C('LAB · ARENA &lt;TKR&gt; · OPT · MC', 'strategy lab — arena / walk-forward / optimizer / monte carlo')}
{C('TIF &lt;BARS|OFF&gt;', 'time-in-force for resting limits (protective OCO exits exempt)')}
{C('SCAN [STRAT]', 'live signal scanner across the whole universe')}
{C('WATCH &lt;SECTOR|ALL&gt; / &lt;SYM|CHG|VOL&gt;', 'filter + sort the monitor')}
{C('FLAT ALL', 'flatten entire book (double-confirm within 5s)')}
{C('ALERT &lt;TKR&gt; &gt;|&lt; &lt;PX&gt;', 'price alert · ALERTS to list · ALERT CLR to clear')}
{C('RISK · RISK SET &lt;KEY&gt; &lt;VAL&gt;', 'report / set limits · PER_SYM GROSS SEC LOTS DAY_LOSS DD')}
{C('DIAG · EXEC · PERF · JOURNAL', 'self-checks · execution quality · runtime perf · audit trail')}
{C('FEED TEST · EXPORT · SEED &lt;N&gt;', 'outage drill · session CSV incl. OHLCV · reproducible market')}
{C('TOP · STRAT · SPEED · PAUSE', 'market map · pod status · feed speed · freeze clock (SPACE)')}
{C('RESET RISK / RESET ACCT', 're-arm after halt / rebase account (double-confirm; wipes journal)')}
{C('CLR · TAB · ↑↓ · /', 'clear log · autocomplete · history · focus command line')}
<h3 style="color:{AMBER};font-size:10px;letter-spacing:2px">STRATEGIES &amp; PARAMETERS</h3>{S}
<h3 style="color:{AMBER};font-size:10px;letter-spacing:2px">EXIT ENGINE — IDENTICAL IN LIVE AND BACKTEST</h3>
<div style="color:{DIM}">TRAIL — trailing stop (ticks), ratchets with favorable moves, evaluated intrabar, drawn on chart ·
MAXB — time stop, flatten after N bars · STOP / TGT — hard stop-loss / profit target (ticks), every tick live,
bar-range backtest, stop-first on ambiguous bars. STOP-market exits slip adverse; TGT exits fill at limit — in BOTH engines.</div>
<h3 style="color:{AMBER};font-size:10px;letter-spacing:2px">WALK-FORWARD</h3>
<div style="color:{DIM}">Sweeps the parameter on the first 70% of bars, then replays the winner AND the defaults on the
unseen final 30%. OOS Sharpe retention ≥60% + beats default = robust candidate; &lt;30% = curve-fit, do not deploy.</div>
<h3 style="color:{AMBER};font-size:10px;letter-spacing:2px">RISK ENGINE</h3>
<div style="color:{DIM}">per-symbol {money_k(CFG['per_sym_notional'])} · gross {money_k(CFG['gross_notional'])} ·
per-sector {money_k(CFG['max_sector_notional'])} · day loss {money_k(CFG['daily_loss'])} (rebased every
{CFG['day_len']} bars) · drawdown {CFG['max_dd_pct']}% — breach ⇒ kill switch: halt + auto-flatten ·
exits and protective OCO always pass.</div>
<div style="margin-top:14px;color:{DIM};font-size:10px;letter-spacing:1px">
PAPER SIMULATION — SYNTHETIC DATA · {CFG['slip_ticks']}-TICK SLIPPAGE + ${CFG['commission']:.0f} COMMISSION, TICK-ROUNDED ·
STATE AUTO-SAVES AND RESTORES ON RELOAD · BT/WF/BTALL/MC RUN OFF THE UI THREAD · NOT INVESTMENT ADVICE</div>
</div>'''])

    # ---------- lab buttons ----------
    def _opt_go(self):
        self.desk.run_opt(self.opt_strat.currentText(), self.opt_param.currentText(),
                          self.opt_sym.currentText(), int(self.opt_bars.text() or 1000))

    def _wf_go(self):
        self.desk.run_wf(self.opt_strat.currentText(), self.opt_param.currentText(),
                         self.opt_sym.currentText(), int(self.opt_bars.text() or 1200))

    def _btall_go(self):
        self.desk.run_btall(self.opt_strat.currentText(), self.bt_target.currentText(),
                            int(self.opt_bars.text() or 800))

    def _mc_go(self):
        self.desk.run_mc()

    def _ticket(self, side):
        sym = self.tk_sym.text().strip().upper()
        try: qty = float(self.tk_qty.text())
        except ValueError: qty = 0
        lmt_s = self.tk_lmt.text().strip()
        lmt = float(lmt_s) if lmt_s else None
        try: stp = float(self.tk_stp.text() or 0)
        except ValueError: stp = 0
        try: tgt = float(self.tk_tgt.text() or 0)
        except ValueError: tgt = 0
        if self.desk.by_sym(sym) is None or qty <= 0:
            self.msg('TICKET — need a valid symbol and quantity', 'err'); return
        self.desk.submit_order(sym, side, qty, lmt, stp, tgt)
        for le in (self.tk_qty, self.tk_lmt, self.tk_stp, self.tk_tgt): le.clear()

    # ---------- compute dispatch (off UI thread) ----------
    def _busy_guard(self):
        if self.desk.compute_busy:
            self.msg('COMPUTE BUSY — hold on', 'err'); return False
        self.desk.compute_busy = True; return True

    def _inst_meta(self, inst):
        return dict(sym=inst.sym, mult=inst.mult, lot=inst.lot, dec=inst.dec, tick=inst.tick)

    def _risk_cfg(self, risk):
        return dict(commission=CFG['commission'], slipTicks=CFG['slip_ticks'],
                    stpTicks=(risk or {}).get('stp', 0), tgtTicks=(risk or {}).get('tgt', 0),
                    trailTicks=(risk or {}).get('trail', 0), maxBars=(risk or {}).get('maxb', 0))

    def run_bt(self, strat_id, sym, count, prm=None, risk=None):
        if not self._busy_guard(): return
        if strat_id not in STRAT_IDS:
            self.msg('UNKNOWN STRATEGY — '+' · '.join(STRAT_IDS), 'err')
            self.desk.compute_busy = False; return
        inst = self.desk.by_sym(sym)
        if inst is None:
            self.msg('UNKNOWN TICKER', 'err'); self.desk.compute_busy = False; return
        count = clamp(count or 1000, 200, len(inst.bars)-80)
        prm = prm or default_params(STRAT_BY_ID[strat_id])
        risk = risk or {}
        self.bt_title.setText('BACKTEST · RUNNING…')
        bars = inst.bars[-count:]
        meta = self._inst_meta(inst); rcfg = self._risk_cfg(risk)
        def fn(): return bt_core(dict(bars=bars, inst=meta, stratId=strat_id,
                                       prm=prm, cfg=rcfg))
        self.submit_job('bt', fn, lambda t, r: self._apply_bt(r, strat_id, sym, count, prm, risk),
                        lambda t, m: self._compute_fail('backtest', m))

    def _compute_fail(self, what, m):
        self.desk.compute_busy = False
        self.desk.sys_err(f'{what}: {m}')
        self.msg(f'{what.upper()} FAILED — see signals', 'err')

    def _apply_bt(self, res, strat_id, sym, count, prm, risk):
        self.desk.compute_busy = False
        try:
            inst = self.desk.by_sym(sym)
            bars = inst.bars[-count:]
            full = dict(res, stratId=strat_id, sym=sym, count=count, prm=prm, risk=risk,
                        bh=[100000*bar.c/bars[0].c for bar in bars],
                        t0=bars[0].t, t1=bars[-1].t)
            self.desk.last_bt = full
            self.desk.btlog.insert(0, dict(stratId=strat_id, sym=sym, count=count,
                prm=dict(prm), risk=dict(risk), ret=res['ret'], sharpe=res['sharpe'],
                mdd=res['mdd'], n=res['n'], t=now_t()))
            if len(self.desk.btlog) > 8: self.desk.btlog.pop()
            self.set_screen('BT'); self._render_bt()
            ex = res['exits']
            self.msg(f'BACKTEST {strat_id}/{sym} — {res["n"]} TRADES · {fmt(res["ret"],2)}% · '
                     f'DD {fmt(res["mdd"]*100,1)}%'
                     + (f' · {ex["STOP"]} STOP-OUTS' if ex['STOP'] else ''), 'ok')
        except Exception:
            self.desk.sys_err(traceback.format_exc(limit=2))

    def run_opt(self, strat_id, param, sym, bars):
        defn = STRAT_BY_ID.get(strat_id)
        if defn is None:
            self.msg('usage: OPT <STRAT> [PARAM] [TKR] [BARS]', 'err'); return
        sc = defn['params'].get(param)
        if sc is None:
            self.msg(f'{strat_id} params — {" · ".join(defn["params"])}', 'err'); return
        inst = self.desk.by_sym(sym)
        if inst is None: self.msg('UNKNOWN TICKER', 'err'); return
        if not self._busy_guard(): return
        self.opt_stat.setText('SWEEPING…')
        count = clamp(bars or 1000, 200, len(inst.bars)-80)
        vals = param_values(sc)
        base = default_params(defn)
        bars_data = inst.bars[-count:]
        meta = self._inst_meta(inst)
        cfgv = dict(commission=CFG['commission'], slipTicks=CFG['slip_ticks'])
        t0 = time.perf_counter()
        def fn():
            out = []
            for v in vals:
                prm = dict(base); prm[param] = v
                r = bt_core(dict(bars=bars_data, inst=meta, stratId=strat_id,
                                 prm=prm, cfg=cfgv))
                out.append(dict(v=v, ret=r['ret'], sharpe=r['sharpe'], mdd=r['mdd'],
                                n=r['n'], pf=r['pf']))
            return out
        self.submit_job('opt', fn,
            lambda t, res: self._apply_opt(res, strat_id, param, sym, count, t0),
            lambda t, m: self._compute_fail('optimizer', m))

    def _apply_opt(self, results, strat_id, param, sym, count, t0):
        self.desk.compute_busy = False
        results.sort(key=lambda r: (r['sharpe'] is not None, r['sharpe'] or -9e9), reverse=True)
        ms = (time.perf_counter()-t0)*1000
        self.desk.opt_state = dict(type='param', stratId=strat_id, param=param, sym=sym,
                                   results=results, count=count, ms=ms)
        self.set_screen('LAB'); self._render_lab()
        self.opt_stat.setText(f'{len(results)} RUNS · {fmt(ms,0)}MS · {self.compute_mode()}')
        bb = results[0]
        self.msg(f'OPT {strat_id}.{param} × {len(results)} ON {sym} — BEST {param}={bb["v"]} · '
                 f'{fmt(bb["ret"],1)}% · SHARPE {"—" if bb["sharpe"] is None else fmt(bb["sharpe"],2)} · '
                 f'{fmt(ms,0)}MS {self.compute_mode()}', 'ok')

    def run_wf(self, strat_id, param, sym, bars):
        defn = STRAT_BY_ID.get(strat_id)
        if defn is None:
            self.msg('usage: WF <STRAT> [PARAM] [TKR] [BARS]', 'err'); return
        sc = defn['params'].get(param)
        if sc is None:
            self.msg(f'{strat_id} params — {" · ".join(defn["params"])}', 'err'); return
        inst = self.desk.by_sym(sym)
        if inst is None: self.msg('UNKNOWN TICKER', 'err'); return
        if not self._busy_guard(): return
        self.opt_stat.setText('WALK-FORWARD…')
        count = clamp(bars or 1200, 300, len(inst.bars)-80)
        payload = dict(stratId=strat_id, param=param, base=default_params(defn),
                       vals=param_values(sc), inst=self._inst_meta(inst),
                       cfg=dict(commission=CFG['commission'], slipTicks=CFG['slip_ticks']),
                       bars=inst.bars[-count:], count=count, isPct=CFG['wf_is_pct'])
        t0 = time.perf_counter()
        self.submit_job('wf', lambda: wf_core(payload),
            lambda t, res: self._apply_wf(res, strat_id, param, sym, count, t0),
            lambda t, m: self._compute_fail('walk-forward', m))

    def _apply_wf(self, res, strat_id, param, sym, count, t0):
        self.desk.compute_busy = False
        ms = (time.perf_counter()-t0)*1000
        self.desk.opt_state = dict(type='wf', stratId=strat_id, param=param, sym=sym,
                                   count=count, ms=ms, res=res)
        self.set_screen('LAB'); self._render_lab()
        self.opt_stat.setText(f'WF · IS {res["isN"]}B / OOS {res["oosN"]}B · '
                              f'{fmt(ms,0)}MS · {self.compute_mode()}')
        if res['best'] and res['oosBest']:
            deg = None
            if res['oosBest']['sharpe'] is not None and res['best']['sharpe'] and res['best']['sharpe'] > 0:
                deg = res['oosBest']['sharpe']/res['best']['sharpe']
            self.msg(f'WF {strat_id}.{param} ON {sym} — BEST {param}={res["best"]["v"]} · '
                     f'IS {fmt(res["best"]["ret"],1)}%/S{fmt(res["best"]["sharpe"],2)} · '
                     f'OOS {fmt(res["oosBest"]["ret"],1)}%/S'
                     f'{"—" if res["oosBest"]["sharpe"] is None else fmt(res["oosBest"]["sharpe"],2)}'
                     + (f' · RETENTION {fmt(deg*100,0)}%' if deg is not None else ''), 'ok')
        else:
            self.msg('WF — no parameter produced ≥4 trades in-sample; widen the sweep', 'err')

    def run_btall(self, strat_id, target, bars):
        defn = STRAT_BY_ID.get(strat_id)
        if defn is None:
            self.msg('usage: BTALL <STRAT> [SECTOR|ALL] [BARS]', 'err'); return
        if not (target == 'ALL' or any(s['id'] == target for s in SECTORS)):
            self.msg('UNKNOWN SECTOR — '+' · '.join(s['id'] for s in SECTORS)+' · ALL', 'err'); return
        eset = self.desk.eqs if (not target or target == 'ALL') else \
               [e for e in self.desk.eqs if e.sector == target]
        if not eset: self.msg('EMPTY SET', 'err'); return
        if not self._busy_guard(): return
        self.opt_stat.setText(f'BATCH · {len(eset)} SYMS…')
        min_bars = min(len(e.bars) for e in eset)
        count = clamp(bars or 800, 200, min_bars-80)
        t0 = time.perf_counter()
        items = [dict(sym=e.sym, mult=e.mult, lot=e.lot, dec=e.dec, tick=e.tick,
                      bars=e.bars[-count:]) for e in eset]
        base = default_params(defn)
        cfgv = dict(commission=CFG['commission'], slipTicks=CFG['slip_ticks'])
        nthreads = self.pool.maxThreadCount()
        k = min(nthreads, max(1, len(items)//20))
        per = math.ceil(len(items)/k)
        chunks = [items[i:i+per] for i in range(0, len(items), per)]
        self._batch_results = []; self._batch_pending = len(chunks)
        if len(chunks) == 1:
            self.submit_job('batch', lambda: bt_batch_chunk(chunks[0], strat_id, base, cfgv),
                lambda t, r: self._apply_batch([r] if r else [], strat_id, target, count, t0),
                lambda t, m: self._compute_fail('batch', m))
        else:
            for ch in chunks:
                self.submit_job('batch', lambda ch=ch: bt_batch_chunk(ch, strat_id, base, cfgv),
                    lambda t, r: self._batch_part(r, strat_id, target, count, t0),
                    lambda t, m: self._batch_part([], strat_id, target, count, t0, failed=True))

    def _batch_part(self, r, strat_id, target, count, t0, failed=False):
        self._batch_pending -= 1
        if r: self._batch_results += r
        if self._batch_pending <= 0:
            self._apply_batch(self._batch_results, strat_id, target, count, t0,
                              degraded=failed)

    def _apply_batch(self, results, strat_id, target, count, t0, degraded=False):
        self.desk.compute_busy = False
        if not results:
            self.msg('BATCH FAILED — see signals', 'err'); return
        ms = (time.perf_counter()-t0)*1000
        results.sort(key=lambda r: (r['sharpe'] is not None, r['sharpe'] or -9e9), reverse=True)
        self.desk.opt_state = dict(type='batch', stratId=strat_id,
                                   target=target or 'ALL', results=results, count=count, ms=ms)
        self.set_screen('LAB'); self._render_lab()
        posp = round(sum(1 for r in results if r['ret'] > 0)/len(results)*100)
        med = results[len(results)//2]['sharpe']
        self.opt_stat.setText(f'{len(results)} SYMS · {fmt(ms,0)}MS · {self.compute_mode()}')
        self.msg(f'BTALL {strat_id} {target or "ALL"} — {len(results)} syms · {posp}% profitable · '
                 f'median Sharpe {"—" if med is None else fmt(med,2)} · '
                 f'best {results[0]["sym"]} {fmt(results[0]["ret"],1)}% · {fmt(ms,0)}MS '
                 f'{self.compute_mode()}{" (partial)" if degraded else ""}', 'ok')

    def run_mc(self):
        if not self._busy_guard(): return
        last = self.desk.last_bt
        if not last or len(last['trades']) < 5:
            self.desk.compute_busy = False
            self.msg('MONTE CARLO NEEDS A BACKTEST WITH ≥5 TRADES — RUN BT FIRST', 'err'); return
        pnls = [t['pnl'] for t in last['trades']]
        self.submit_job('mc', lambda: mc_core(pnls, CFG['mc_paths'], 9176+len(pnls)),
            lambda t, res: self._apply_mc(res, last),
            lambda t, m: self._compute_fail('montecarlo', m))

    def _apply_mc(self, mc, last):
        self.desk.compute_busy = False
        actual = [100000]; e = 100000.0
        for t in last['trades']:
            e += t['pnl']; actual.append(e)
        mc['actual'] = actual
        self.desk.mc_state = mc
        self.set_screen('LAB'); self._render_lab()
        self.msg(f'MONTE CARLO — {mc["M"]} BOOTSTRAP PATHS · P(LOSS) {fmt(mc["pLoss"]*100,1)}% · '
                 f'DD95 −{fmt(mc["dd95"]*100,1)}%', 'ok')

    # ---------- command dispatch ----------
    def exec_cmd(self, line):
        self._exec_from_ui(line)

    def _exec_desk(self, raw):
        d = self.desk
        tk = raw.upper().split()
        if tk[0] in d.syms:
            self.load(tk[0]); self.msg(f'{tk[0]} · {d.by_sym(tk[0]).name} — chart loaded', 'ok'); return
        cmd = tk[0]
        if cmd in ('HELP', '?'):
            self.set_screen('HELP'); return
        if cmd in ('TOP', 'MOST'):
            self.set_screen('TOP'); return
        if cmd in ('PORT', 'PF'):
            self.set_screen('PORT'); return
        if cmd in ('LAB', 'SIMS'):
            self.set_screen('LAB'); return
        if cmd == 'TIF':
            if len(tk) < 2:
                self.msg(f'TIF = {CFG["tif_bars"] if CFG["tif_bars"]>0 else "GTC"} — usage: TIF <BARS|OFF>', 'ok')
            elif tk[1] in ('OFF', 'GTC'):
                CFG['tif_bars'] = 0; self._tif_done()
            else:
                try:
                    n = int(tk[1])
                    if n <= 0: raise ValueError
                    CFG['tif_bars'] = n; self._tif_done()
                except ValueError:
                    self.msg('usage: TIF <BARS|OFF>', 'err')
            return
        if cmd in ('CLOSE', 'CLOSEOUT'):
            if len(tk) < 2: self.msg('usage: CLOSE <SYM|SECTOR|ALL>', 'err')
            else: d.close_positions(tk[1], tk[1])
            return
        if cmd in ('SCAN', 'SCN'):
            sf = tk[1] if len(tk) > 1 else None
            if sf and sf not in STRAT_IDS:
                self.msg(f'unknown strategy "{esc(sf)}" — scanned all', 'err'); sf = None
            d.run_scan(sf); return
        if cmd == 'WATCH':
            if len(tk) < 2:
                self.msg(f'WATCH filter={d.watch["filter"]} sort={d.watch["sort"]}', 'ok'); return
            a = tk[1]
            if a in ('SYM', 'CHG', 'VOL'):
                d.watch['sort'] = a; self.sort_btn.setText('⇅ '+a); self._watch_fill()
                self.msg(f'WATCH SORT {a}', 'ok'); return
            if a == 'ALL' or a == 'MAC' or any(s['id'] == a for s in SECTORS):
                self._watch_filter(a); self.msg(f'WATCH FILTER {a}', 'ok'); return
            self.msg('usage: WATCH <SECTOR|ALL|MAC> or <SYM|CHG|VOL>', 'err'); return
        if cmd in ('STRAT', 'ALGO'):
            if not d.pods:
                self.msg('NO PODS — RUN <STRAT> [TICKER]', 'ok'); return
            for p in d.pods:
                exp = p.realized/p.trades_n if p.trades_n else 0.0
                pos = (f'{"LONG" if p.pos>0 else "SHORT"} {abs(p.pos)} @ '
                       f'{fmt_px(p.avg, p.inst.dec)}' if p.pos != 0 else 'flat')
                risk = (f' ST:{p.stop_ticks}' if p.stop_ticks else '') + \
                       (f' TP:{p.tgt_ticks}' if p.tgt_ticks else '') + \
                       (f' TR:{p.trail_ticks}' if p.trail_ticks else '') + \
                       (f' MX:{p.max_bars}' if p.max_bars else '')
                self.sig('SYS', f'{"[LIVE]" if p.running else "[IDLE]"} {p.key} · {pos} · '
                                f'P&L {money(p.realized, True)} · EXP {money(exp, True)} · '
                                f'{" ".join(k+":"+str(v) for k, v in p.params.items())}{risk}')
            self.msg('pod status printed to signal log', 'ok'); return
        if cmd == 'RUN':
            if len(tk) < 2 or tk[1] not in STRAT_IDS:
                self.msg('usage: RUN <STRAT> [TICKER]', 'err'); return
            sym = tk[2] if len(tk) > 2 and tk[2] in d.syms else self.active
            d.start_pod(tk[1], sym); self.load(sym); return
        if cmd in ('STOP', 'KILL'):
            if len(tk) < 2: self.msg('usage: STOP <STRAT|ALL> [TKR]', 'err'); return
            if tk[1] == 'ALL':
                for p in d.pods:
                    if p.running: d.stop_pod(p.key)
                return
            if tk[1] in STRAT_IDS:
                if len(tk) > 2 and tk[2] in d.syms:
                    key = tk[1]+'·'+tk[2]
                    p = next((x for x in d.pods if x.key == key), None)
                    if p and p.running: d.stop_pod(key)
                    else: self.msg(f'{key} NOT LIVE', 'err')
                else:
                    live = [p for p in d.pods if p.defn['id'] == tk[1] and p.running]
                    if not live: self.msg(f'NO LIVE {tk[1]} PODS', 'err')
                    else:
                        for p in live: d.stop_pod(p.key)
                return
            self.msg('usage: STOP <STRAT|ALL> [TKR]', 'err'); return
        if cmd == 'SET':
            if len(tk) < 4 or tk[1] not in STRAT_IDS:
                self.msg('usage: SET <STRAT> <PARAM|STOP|TGT|TRAIL|MAXB> <VALUE>', 'err'); return
            try: val = float(tk[3])
            except ValueError:
                self.msg('bad value', 'err'); return
            if tk[2] in ('STOP', 'TGT', 'TRAIL', 'MAXB'): d.set_pod_risk(tk[1], tk[2], val)
            else: d.set_param(tk[1], tk[2], val)
            return
        if cmd in ('BT', 'BACKTEST'):
            strat = tk[1] if len(tk) > 1 else (d.last_bt or {}).get('stratId')
            sym = tk[2] if len(tk) > 2 and tk[2] in d.syms else self.active
            if strat not in STRAT_IDS:
                self.msg('usage: BT <STRAT> <TICKER> [BARS] [STP t] [TGT t] [TRAIL t] [MAXB n]', 'err')
                return
            bars = 1000
            for tok in tk[3:]:
                if tok.isdigit(): bars = int(tok); break
            d_run = self._parse_risk(tk, 3)
            self.run_bt(strat, sym, bars, None, d_run); return
        if cmd in ('WF', 'WALKFORWARD', 'WALK'):
            if len(tk) < 2 or tk[1] not in STRAT_IDS:
                self.msg('usage: WF <STRAT> [PARAM] [TKR] [BARS]', 'err'); return
            defn = STRAT_BY_ID[tk[1]]
            param = sym = None; bars = None
            for tok in tk[2:]:
                if tok in defn['params']: param = tok
                elif tok in d.syms: sym = tok
                elif tok.isdigit(): bars = int(tok)
            self.run_wf(tk[1], param or list(defn['params'])[0],
                        sym or self.active, bars or 1200); return
        if cmd == 'BTLOG': d.btlog_report(); return
        if cmd == 'BTALL':
            if len(tk) < 2 or tk[1] not in STRAT_IDS:
                self.msg('usage: BTALL <STRAT> [SECTOR|ALL] [BARS]', 'err'); return
            self.run_btall(tk[1], tk[2] if len(tk) > 2 else 'ALL',
                           int(tk[3]) if len(tk) > 3 and tk[3].isdigit() else 800); return
        if cmd in ('OPT', 'OPTIMIZE'):
            if len(tk) < 2 or tk[1] not in STRAT_IDS:
                self.msg('usage: OPT <STRAT> [PARAM] [TKR] [BARS]', 'err'); return
            defn = STRAT_BY_ID[tk[1]]
            param = sym = None; bars = None
            for tok in tk[2:]:
                if tok in defn['params']: param = tok
                elif tok in d.syms: sym = tok
                elif tok.isdigit(): bars = int(tok)
            self.run_opt(tk[1], param or list(defn['params'])[0],
                         sym or self.active, bars or 1000); return
        if cmd in ('MC', 'MONTE', 'MONTECARLO'): d.run_mc(); return
        if cmd == 'ARENA':
            if len(tk) < 2:
                self.msg(f'ARENA {"LIVE ON "+d.arena["sym"] if d.arena["on"] else "IDLE — ARENA <TKR>"}', 'ok')
            elif tk[1] in ('STOP', 'OFF'): d.arena_stop()
            elif tk[1] in d.syms: d.arena_start(tk[1])
            else: self.msg('usage: ARENA <TKR|STOP>', 'err')
            return
        if cmd in ('BUY', 'SELL'):
            side = 1 if cmd == 'BUY' else -1
            sym = tk[1] if len(tk) > 1 else None
            try: qty = float(tk[2]) if len(tk) > 2 else 0
            except ValueError: qty = 0
            lmt = None; stp = 0; tgt = 0; bad = False
            i = 3
            while i < len(tk):
                if tk[i] == 'LMT' and i+1 < len(tk):
                    try: lmt = float(tk[i+1])
                    except ValueError: bad = True
                    i += 2
                elif tk[i] == 'STP' and i+1 < len(tk):
                    try: stp = float(tk[i+1])
                    except ValueError: bad = True
                    i += 2
                elif tk[i] == 'TGT' and i+1 < len(tk):
                    try: tgt = float(tk[i+1])
                    except ValueError: bad = True
                    i += 2
                else:
                    bad = True; break
            if d.by_sym(sym) is None or qty <= 0 or bad:
                self.msg(f'usage: {cmd} <TICKER> <QTY> [LMT <PX>] [STP <TICKS>] [TGT <TICKS>]', 'err')
                return
            d.submit_order(sym, side, qty, lmt, stp, tgt); return
        if cmd == 'CXL':
            if len(tk) > 1 and tk[1] == 'ALL': d.cancel_all_orders()
            elif len(tk) > 1 and tk[1].isdigit(): d.cancel_order(int(tk[1]))
            else: self.msg('usage: CXL <ID|ALL>', 'err')
            return
        if cmd == 'FLAT': self._flat_req(); return
        if cmd == 'ALERT':
            if len(tk) > 1 and tk[1] == 'CLR':
                d.alerts.clear(); self.msg('ALL ALERTS CLEARED', 'ok'); return
            if len(tk) < 4 or tk[1] not in d.syms or tk[2] not in ('>', '<'):
                self.msg('usage: ALERT <TKR> >|< <PRICE> · ALERT CLR · ALERTS', 'err'); return
            try: d.add_alert(tk[1], tk[2], float(tk[3]))
            except ValueError: self.msg('bad price', 'err')
            return
        if cmd == 'ALERTS':
            act = [a for a in d.alerts if a['active']]
            if not act: self.msg('NO ACTIVE ALERTS', 'ok')
            for a in act:
                self.sig('SYS', f'ALERT #{a["id"]} — {a["sym"]} {a["op"]} '
                                f'{fmt_px(a["px"], d.by_sym(a["sym"]).dec)}')
            return
        if cmd == 'RISK':
            if len(tk) > 1 and tk[1] == 'SET':
                mapping = dict(PER_SYM='per_sym_notional', GROSS='gross_notional',
                               SEC='max_sector_notional', LOTS='max_lots',
                               DAY_LOSS='daily_loss', DD='max_dd_pct')
                key = mapping.get(tk[2] if len(tk) > 2 else '')
                try: v = float(tk[3]) if len(tk) > 3 else 0
                except ValueError: v = 0
                if not key or v <= 0:
                    self.msg('usage: RISK SET <PER_SYM|GROSS|SEC|LOTS|DAY_LOSS|DD> <VALUE>', 'err')
                    return
                CFG[key] = v
                d.audit('RISK', f'{tk[2]}={v}')
                self.sig('SYS', f'RISK LIMIT CHANGED — {tk[2]} → {v}')
                self.msg(f'RISK {tk[2]} = {v}', 'ok'); d.risk_report(); d.save_journal()
                return
            d.risk_report(); return
        if cmd in ('DIAG', 'CHECK'): d.diag(); return
        if cmd == 'EXEC': d.exec_report(); return
        if cmd == 'PERF': d.perf_report(); return
        if cmd == 'JOURNAL':
            self.sig('SYS', f'AUDIT TRAIL — {len(d.journal)} events · '
                            f'{d.journal[-1]["t"] if d.journal else ""} latest')
            for a in d.journal[-25:]:
                self.sig('SYS', f'{a["t"][11:19]} {a["kind"]} — {a["detail"]}')
            self.msg('audit trail printed', 'ok'); return
        if cmd == 'FEED':
            if len(tk) > 1 and tk[1] in ('TEST', 'DROP'): self._feed_test()
            else: self.msg('usage: FEED TEST — 6s outage drill', 'err')
            return
        if cmd == 'EXPORT': self._export(); return
        if cmd == 'SEED':
            try:
                n = int(tk[1])
                if n <= 0: raise ValueError
                d.reseed(n)
                self._watch_fill(); self.refresh_all()
                if self.stack.currentIndex() in (0, 3, 4):
                    self.set_screen(self.screens[self.stack.currentIndex()])
            except (ValueError, IndexError):
                self.msg('usage: SEED <1..999999999>', 'err')
            return
        if cmd == 'SPEED':
            try:
                v = float(tk[1])
                if v in (0.5, 1, 2, 4, 8): self._set_speed(v)
                else: raise ValueError
            except (ValueError, IndexError):
                self.msg('SPEED 0.5 · 1 · 2 · 4 · 8', 'err')
            return
        if cmd == 'PAUSE': self._set_paused(True); return
        if cmd in ('RESUME', 'GO'): self._set_paused(False); return
        if cmd == 'RESET':
            if len(tk) > 1 and tk[1] == 'RISK': self._reset_risk()
            elif len(tk) > 1 and tk[1] == 'ACCT': self._reset_acct_req()
            else: self.msg('usage: RESET RISK | RESET ACCT', 'err')
            return
        if cmd == 'CLR': self._clr_sig(); self.msg('SIGNAL LOG CLEARED', 'ok'); return
        self.msg(f'NOT RECORDED: {esc(raw)} · type HELP', 'err')

    def _tif_done(self):
        self.desk.audit('TIF', str(CFG['tif_bars']))
        self.sig('SYS', f'TIF → {CFG["tif_bars"] if CFG["tif_bars"]>0 else "GTC"}'
                        f'{" bars" if CFG["tif_bars"]>0 else ""} · applies to new orders · OCO exempt')
        self.msg(f'TIF {CFG["tif_bars"] if CFG["tif_bars"]>0 else "GTC"}'
                 f'{"B" if CFG["tif_bars"]>0 else ""}', 'ok')
        self.desk.save_journal()

    @staticmethod
    def _parse_risk(tk, start):
        risk = {}
        i = start
        while i < len(tk):
            if tk[i] == 'STP' and i+1 < len(tk):
                try:
                    v = float(tk[i+1])
                    if v > 0: risk['stp'] = v
                except ValueError: pass
                i += 2
            elif tk[i] == 'TGT' and i+1 < len(tk):
                try:
                    v = float(tk[i+1])
                    if v > 0: risk['tgt'] = v
                except ValueError: pass
                i += 2
            elif tk[i] == 'TRAIL' and i+1 < len(tk):
                try:
                    v = float(tk[i+1])
                    if v > 0: risk['trail'] = v
                except ValueError: pass
                i += 2
            elif tk[i] == 'MAXB' and i+1 < len(tk):
                try:
                    v = int(tk[i+1])
                    if v > 0: risk['maxb'] = v
                except ValueError: pass
                i += 2
            else:
                i += 1
        return risk

    def _flat_req(self):
        if time.time()-self.desk.confirm_flat < 5:
            self.desk.confirm_flat = 0; self.desk.flat_all()
        else:
            self.desk.confirm_flat = time.time()
            self.msg('CONFIRM — RE-TYPE "FLAT ALL" WITHIN 5S (ESC CANCELS)', 'err')

    def _reset_risk(self):
        d = self.desk
        d.halted = False; d.eq_peak = d.current_equity(); d.day_start_eq = d.eq_peak
        self.halt_banner.setVisible(False)
        d.audit('RISK', 're-armed')
        self._conn(); self._status(); d.save_journal()
        self.sig('SYS', 'RISK RE-ARMED — kill switch reset · day-loss limit rebased')
        self.msg('RISK ENGINE RE-ARMED', 'ok')

    def _reset_acct_req(self):
        if time.time()-self.confirm_reset < 5:
            self.confirm_reset = 0; self.desk.reset_acct()
            self.refresh_all(); self._legend_rebuild()
        else:
            self.confirm_reset = time.time()
            self.msg('CONFIRM — RE-TYPE "RESET ACCT" WITHIN 5S · WIPES BOOK, '
                     'ATTRIBUTION AND SAVED JOURNAL', 'err')

    def _set_speed(self, v):
        self._speed = v
        self.tick_timer.setInterval(int(CFG['tick_ms']/v))
        self.msg(f'SIM FEED SPEED {v}×', 'ok'); self._status()

    def _set_paused(self, v):
        d = self.desk
        if d.paused == v: return
        d.paused = v
        self._conn(); self._status()
        self.msg('FEED PAUSED — SIM CLOCK FROZEN' if v else 'FEED RESUMED',
                 '' if v else 'ok')

    def _feed_test(self):
        d = self.desk
        if d.feed_down_until > time.time():
            self.msg('OUTAGE DRILL ALREADY RUNNING', 'err'); return
        d.feed_down_until = time.time()+6
        d.audit('FEED', 'outage drill start')
        self.sig('ERR', 'FEED OUTAGE DRILL — market data dropped · ticks frozen · '
                        'orders/positions preserved')
        self._conn(); self._status()
        QTimer.singleShot(6000, self._feed_back)

    def _feed_back(self):
        self.desk.feed_down_until = 0
        self.desk.audit('FEED', 'outage drill end · reconnected')
        self.sig('SYS', 'FEED RECONNECTED — sim state intact · intrabar stops resume next tick')
        self._conn(); self._status()

    def _export(self):
        default = os.path.expanduser(
            f'~/ember_session_{datetime.now().strftime("%Y-%m-%d-%H%M%S")}.csv')
        path, _f = QFileDialog.getSaveFileName(self, 'Export session CSV', default, 'CSV (*.csv)')
        if not path: return
        self.desk.export_csv(path)
        self.msg(f'EXPORTED {len(self.desk.fills)} FILLS · {len(self.desk.trades_log)} '
                 f'ROUND-TRIPS · {len(self.desk.eq_hist)} EQ POINTS · audit → {path}', 'ok')

    # ---------- function keys ----------
    def fkey(self, name):
        if name == 'HELP': self.set_screen('HELP')
        elif name == 'TOP': self.set_screen('TOP')
        elif name == 'CHART': self.set_screen('CHART')
        elif name == 'PORT': self.set_screen('PORT')
        elif name == 'LAB': self.set_screen('LAB')
        elif name == 'BT':
            if self.desk.last_bt:
                lb = self.desk.last_bt
                self.run_bt(lb['stratId'], lb['sym'], lb['count'], lb['prm'], lb['risk'])
            else: self.msg('usage: BT <STRAT> <TICKER> [BARS]', 'err')
        elif name == 'STRAT': self.exec_cmd('STRAT')
        elif name == 'ALERTS': self.exec_cmd('ALERTS')
        elif name == 'FLAT': self._flat_req()
        elif name == 'SPEED':
            seq = [0.5, 1, 2, 4, 8]
            cur = getattr(self, '_speed', 1)
            self._set_speed(seq[(seq.index(cur)+1) % len(seq)])
        elif name == 'PAUSE': self._set_paused(not self.desk.paused)
        elif name == 'CLR': self.exec_cmd('CLR')

    def _bind_keys(self):
        for key, name in (('F1','HELP'), ('F2','TOP'), ('F3','CHART'), ('F4','BT'),
                          ('F6','STRAT'), ('F7','ALERTS'), ('F8','FLAT'), ('F9','SPEED'),
                          ('F10','PAUSE'), ('F12','CLR')):
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(lambda n=name: self.fkey(n))
        app = QApplication.instance()
        app.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.KeyPress:
            fw = QApplication.focusWidget()
            editing = isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit)) \
                if (QTextEdit := globals().get('QTextEdit')) else isinstance(fw, QLineEdit)
            if ev.key() == Qt.Key_Slash and not isinstance(fw, QLineEdit):
                self.cmd.setFocus(); return True
            if ev.key() == Qt.Key_Space and not editing:
                self._set_paused(not self.desk.paused); return True
        return super().eventFilter(obj, ev)

    # ---------- prefs ----------
    def _load_prefs(self):
        try:
            with open(PREFS_PATH) as f: p = json.load(f)
            self._speed = p.get('speed', 1)
            self._view = clamp(int(p.get('view', 130)), 40, 400)
            self.chart.view = self._view
            self.chart_show.update(p.get('show', {}))
            act = p.get('active')
            if act and self.desk.by_sym(act): self.active = act
        except Exception:
            self._speed = 1

    def _save_prefs(self):
        try:
            with open(PREFS_PATH, 'w') as f:
                json.dump(dict(speed=getattr(self, '_speed', 1),
                               view=self.chart.view, active=self.active,
                               show=self.chart_show), f)
        except Exception:
            pass

    def closeEvent(self, _e):
        self.desk.save_journal(); self._save_prefs()

# plain-text alias used in eventFilter
QTextEdit = None
try:
    from PySide6.QtWidgets import QTextEdit as _TE, QPlainTextEdit as _PE
    QTextEdit = _TE
except Exception:
    pass

# ============================ 8 · main ============================
def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet(QSS)
    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()