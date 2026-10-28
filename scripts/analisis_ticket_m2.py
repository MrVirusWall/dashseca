#!/usr/bin/env python3
"""Comparativo interanual de ventas, visitas, efectividad, ticket promedio y precio por m2.

Lee el Google Sheet de Secaforte (hojas presupuestoProspecto, productoPresupuesto, visitas)
vía gviz CSV, igual que index.html. Solo usa la librería estándar.

Uso:
  python3 scripts/analisis_ticket_m2.py
  python3 scripts/analisis_ticket_m2.py --csv-dir ./export   # si exportaste las hojas a CSV
"""
import argparse, csv, io, os, re, sys, urllib.parse, urllib.request
from collections import defaultdict
from datetime import date

SHEET_ID = '1PwYUmaX800n4H_kYGWlqleAbdS5h3bBivHswaAMem6Y'
HOY = date.today()
# Meses a comparar: (mes, año base, año actual)
MESES = [(9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre')]
ANIO_PREV, ANIO_ACT = HOY.year - 1, HOY.year


def leer_hoja(nombre, csv_dir=None):
    if csv_dir:
        with open(os.path.join(csv_dir, nombre + '.csv'), encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))
    url = (f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv'
           f'&sheet={urllib.parse.quote(nombre)}')
    with urllib.request.urlopen(url, timeout=120) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode('utf-8-sig'))))


def parse_fecha(s):
    """Acepta dd/mm/yyyy [hh:mm:ss] y yyyy-mm-dd [hh:mm:ss]."""
    s = (s or '').strip()
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if m:
        return date(int(m[3]), int(m[2]), int(m[1]))
    m = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})', s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    return None


def parse_num(s):
    """'$3,532.99' -> 3532.99 ; '1.234,56' -> 1234.56"""
    s = re.sub(r'[^\d,.\-]', '', str(s or ''))
    if not s:
        return 0.0
    if ',' in s and '.' in s:
        s = s.replace(',', '') if s.rfind('.') > s.rfind(',') else s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.') if len(s.split(',')[-1]) <= 2 else s.replace(',', '')
    try:
        return float(s)
    except ValueError:
        return 0.0


def mismo_periodo(d, mes, anio):
    """Mes completo, salvo el mes en curso del año actual (hasta hoy) y su equivalente del año previo."""
    if d is None or d.year != anio or d.month != mes:
        return False
    if anio == ANIO_ACT and mes == HOY.month:
        return d <= HOY
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv-dir', help='carpeta con presupuestoProspecto.csv, productoPresupuesto.csv, visitas.csv')
    a = ap.parse_args()

    pres = leer_hoja('presupuestoProspecto', a.csv_dir)
    prod = leer_hoja('productoPresupuesto', a.csv_dir)
    vis = leer_hoja('visitas', a.csv_dir)

    estados = defaultdict(int)
    for p in pres:
        estados[p.get('Estado_Presupuesto', '')] += 1
    print('Estados de presupuesto encontrados:', dict(estados), file=sys.stderr)

    m2_por_pres = defaultdict(float)
    for r in prod:
        m2_por_pres[r.get('ID_PresupuestoProspecto') or r.get('ID_PresupuestoProsp...', '')] += parse_num(r.get('CantidadM2_ProductoPresupuesto', r.get('CantidadM2_Producto...', 0)))
    if not m2_por_pres:
        # nombres de columna truncados/distintos: buscar por prefijo
        for r in prod:
            k_id = next((k for k in r if k.startswith('ID_PresupuestoPros')), None)
            k_m2 = next((k for k in r if k.startswith('CantidadM2')), None)
            m2_por_pres[r[k_id]] += parse_num(r[k_m2])

    # clave -> métricas
    datos = defaultdict(lambda: {'ventas': 0, 'monto': 0.0, 'm2': 0.0, 'm2_ventas': 0, 'visitas': 0, 'monedas': set()})
    for p in pres:
        if p.get('Estado_Presupuesto', '').strip().lower() != 'vendido':
            continue
        d = parse_fecha(p.get('Fecha_Venta'))
        for mes, _ in MESES:
            for anio in (ANIO_PREV, ANIO_ACT):
                if mismo_periodo(d, mes, anio):
                    k = datos[(anio, mes)]
                    k['ventas'] += 1
                    k['monto'] += parse_num(p.get('Total_Presupuesto'))
                    k['monedas'].add(p.get('Moneda_Presupuesto', ''))
                    m2 = m2_por_pres.get(p.get('ID_Presupuesto'), 0.0)
                    k['m2'] += m2
                    k['m2_ventas'] += 1 if m2 > 0 else 0
    for v in vis:
        if v.get('Estado_Visita', '').strip().lower() != 'realizada':
            continue
        d = parse_fecha(v.get('FechaHora_Visita'))
        for mes, _ in MESES:
            for anio in (ANIO_PREV, ANIO_ACT):
                if mismo_periodo(d, mes, anio):
                    datos[(anio, mes)]['visitas'] += 1

    def fila(k):
        ventas, monto, m2, vis_ = k['ventas'], k['monto'], k['m2'], k['visitas']
        return {
            'Ventas': ventas,
            'Visitas realizadas': vis_,
            'Efectividad %': 100 * ventas / vis_ if vis_ else 0,
            'Monto vendido': monto,
            'Ticket promedio': monto / ventas if ventas else 0,
            'M2 vendidos': m2,
            'Precio por m2': monto / m2 if m2 else 0,
            'Ventas con m2 cargado': f"{k['m2_ventas']}/{ventas}",
        }

    def var(a_, b_):
        return f'{100 * (b_ - a_) / a_:+.1f}%' if a_ else 'n/d'

    print(f'\nComparativo {ANIO_PREV} vs {ANIO_ACT} (mes en curso hasta {HOY:%d/%m/%Y})\n')
    for mes, nombre in MESES:
        prev, act = fila(datos[(ANIO_PREV, mes)]), fila(datos[(ANIO_ACT, mes)])
        monedas = datos[(ANIO_PREV, mes)]['monedas'] | datos[(ANIO_ACT, mes)]['monedas']
        print(f'== {nombre} ==  monedas en ventas: {sorted(monedas) or "-"}')
        print(f'{"":24}{ANIO_PREV:>14}{ANIO_ACT:>14}{"Var.":>10}')
        for c in prev:
            if c == 'Ventas con m2 cargado':
                print(f'{c:24}{prev[c]:>14}{act[c]:>14}')
                continue
            fmt = (lambda x: f'{x:,.1f}') if isinstance(prev[c], float) else (lambda x: f'{x:,}')
            print(f'{c:24}{fmt(prev[c]):>14}{fmt(act[c]):>14}{var(prev[c], act[c]):>10}')
        print()
    print('Nota: si hay ventas en más de una moneda, el monto y el precio por m2 mezclan monedas; revisar la línea "monedas".')
    print('Nota: "Ventas con m2 cargado" indica en cuántas ventas existe detalle en productoPresupuesto.')


if __name__ == '__main__':
    main()
