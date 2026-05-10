"""Render Blender shader graphs to SVG using node positions captured from bpy.
Run with the bundled blender python on the *_pos_*.json files.
"""
import json, os, sys, html, re

OUT_DIR = 'C:/Users/14047/Documents/VS Code Scripts/blender-render-pipeline/workspace/project/notes/shader_diagrams'
os.makedirs(OUT_DIR, exist_ok=True)

# (material_name, node_name) -> edit instruction shown next to the node
HIGHLIGHTS = {
    ('Ch03_Body', 'LO_083 narrow hatch A ramp'):
        'EDIT: stops 0.49/0.55 -> 0.35/0.62 (try Linear interp for softer hatch)',
    ('Ch03_Body', 'LO_083 hatch breakup ramp'):
        'EDIT: stops 0.4/0.65 -> 0.25/0.75 (lets breakup wave actually fragment lines)',
    ('Ch03_Body', 'LO_083 crosshatch diagonal mapping A'):
        'EDIT: Scale (20,20,20); rotate Z to taste (controls hatch density + angle)',
    ('Ch03_Body', 'LO_083 downloaded-style breakup wave'):
        'EDIT: Distortion 0 -> 2.0-4.0 (organic break-up)',
    ('Ch03_Body', 'LO_083 local color dot size ramp'):
        'EDIT: stops 0.018/0.034 -> 0.05/0.12 (bigger softer screentone dots)',
    ('Ch03_Body', 'LO_083 magenta bleed 1 dot size ramp'):
        'EDIT: stops 0.014/0.03 -> 0.04/0.10',
    ('Ch03_Body', 'LO_083 magenta bleed 2 dot size ramp'):
        'EDIT: stops 0.014/0.024 -> 0.04/0.10',
}

# Color per node category (Blender-ish palette)
CATEGORY_COLOR = {
    'Output':    '#cc4444',
    'Shader':    '#5a8b48',  # BSDFs, emission
    'Color':     '#a07740',  # mix, ramp, gamma, brightcontrast, hue
    'Texture':   '#664488',  # tex* nodes
    'Vector':    '#4477aa',  # mapping, vectormath, normalmap
    'Converter': '#577a8a',  # shader-to-rgb, math, value, rgb, separate, combine
    'Input':     '#8aa6c2',  # texcoord, geometry, fresnel, layer weight
    'Group':     '#446677',
    'Other':     '#555555',
}
def categorize(t):
    t = t.replace('ShaderNode','')
    if 'Output' in t: return 'Output'
    if t in ('BsdfPrincipled','BsdfDiffuse','BsdfTranslucent','BsdfTransparent','Emission','BsdfGlossy','BsdfRefraction','MixShader','AddShader','Holdout'): return 'Shader'
    if t in ('MixRGB','Mix','ValToRGB','Gamma','BrightContrast','HueSaturation','Invert'): return 'Color'
    if t.startswith('Tex'): return 'Texture'
    if t in ('Mapping','VectorMath','NormalMap','Bump','VectorRotate','VectorTransform'): return 'Vector'
    if t in ('ShaderToRGB','Math','Value','RGB','SeparateXYZ','CombineXYZ','SeparateColor','CombineColor','Clamp','MapRange'): return 'Converter'
    if t in ('TexCoord','Geometry','LayerWeight','Fresnel','ObjectInfo','HairInfo','LightPath','UVMap','Attribute','VertexColor'): return 'Input'
    if t == 'Group': return 'Group'
    return 'Other'

def short_label(n):
    if n.get('label'): return n['label']
    return n['type'].replace('ShaderNode','')

def detail_lines(n):
    lines = []
    t = n['type']
    if t == 'ShaderNodeTexWave':
        lines.append(f"wave {n.get('wave_type')}/{n.get('bands_direction','')} {n.get('wave_profile','')}")
        for k in ('in:Scale','in:Distortion','in:Detail'):
            if k in n: lines.append(f"{k[3:]}={n[k]}")
    elif t == 'ShaderNodeTexVoronoi':
        lines.append(f"{n.get('feature')} / {n.get('distance')} / {n.get('dim')}")
        for k in ('in:Scale','in:Randomness','in:Smoothness'):
            if k in n: lines.append(f"{k[3:]}={n[k]}")
    elif t == 'ShaderNodeValToRGB':
        lines.append(f"ramp: {n.get('interpolation','')}")
        stops = n.get('elements',[])
        for e in stops[:4]:
            c = e['color']
            hexc = '#%02x%02x%02x' % (int(c[0]*255), int(c[1]*255), int(c[2]*255))
            lines.append(f"  stop@{e['pos']:.2f} {hexc}")
    elif t in ('ShaderNodeMixRGB','ShaderNodeMix'):
        bt = n.get('blend_type','')
        if bt: lines.append(f"mix: {bt}")
    elif t == 'ShaderNodeMath':
        lines.append(f"op: {n.get('operation','')}")
    elif t == 'ShaderNodeRGB':
        c = n.get('in:Color') or n.get('color')
        if c and isinstance(c,list):
            hexc = '#%02x%02x%02x' % (int(c[0]*255), int(c[1]*255), int(c[2]*255))
            lines.append(f"color {hexc}")
    elif t == 'ShaderNodeValue':
        v = n.get('value') or n.get('in:Value')
        if v is not None: lines.append(f"value {v}")
    return lines

# Layout constants — Blender uses Y-down conceptually but stores Y as up; we'll flip.
NODE_W = 220
TITLE_H = 22
LINE_H = 13
PAD = 10

def render_material(mat_name, mat, out_path):
    nodes = mat['nodes']
    if not nodes:
        return
    # Compute bbox
    xs=[]; ys=[]
    node_lookup = {}
    for n in nodes:
        x = n['x']; y = -n['y']  # flip
        n['_x']=x; n['_y']=y
        details = detail_lines(n)
        n['_details']=details
        h = TITLE_H + LINE_H*(1+len(details)) + PAD
        n['_h']=h
        xs += [x, x+NODE_W]
        ys += [y, y+h]
        node_lookup[n['name']] = n

    minx=min(xs)-50; maxx=max(xs)+50
    miny=min(ys)-50; maxy=max(ys)+50
    W = maxx-minx; H = maxy-miny

    svg = []
    svg.append(f'<?xml version="1.0" encoding="UTF-8"?>')
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{minx} {miny} {W} {H}" width="{int(W*0.7)}" height="{int(H*0.7)}" font-family="Consolas, monospace" font-size="11">')
    # Yellow glow filter for highlighted nodes
    svg.append('<defs><filter id="glow" x="-50%" y="-50%" width="200%" height="200%">'
               '<feGaussianBlur stdDeviation="6" result="blur"/>'
               '<feFlood flood-color="#ffd400" flood-opacity="1"/>'
               '<feComposite in2="blur" operator="in"/>'
               '<feMerge><feMergeNode/><feMergeNode/><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge>'
               '</filter></defs>')
    svg.append(f'<rect x="{minx}" y="{miny}" width="{W}" height="{H}" fill="#2b2b2b"/>')
    svg.append(f'<text x="{minx+20}" y="{miny+30}" fill="#eee" font-size="18">{html.escape(mat_name)}</text>')

    highlight_count = sum(1 for n in nodes if (mat_name, n['name']) in HIGHLIGHTS)
    if highlight_count:
        svg.append(f'<text x="{minx+20}" y="{miny+52}" fill="#ffd400" font-size="13">'
                   f'{highlight_count} nodes need editing — glowing yellow below</text>')

    # Links — drawn first so nodes overlay
    for l in mat['links']:
        a = node_lookup.get(l['from_node']); b = node_lookup.get(l['to_node'])
        if not a or not b: continue
        x1 = a['_x'] + NODE_W; y1 = a['_y'] + TITLE_H/2 + 4
        x2 = b['_x']; y2 = b['_y'] + TITLE_H/2 + 4
        cx = (x1+x2)/2
        path = f'M {x1} {y1} C {cx} {y1}, {cx} {y2}, {x2} {y2}'
        svg.append(f'<path d="{path}" fill="none" stroke="#cccccc" stroke-width="1.4" opacity="0.75"/>')

    # Nodes
    for n in nodes:
        cat = categorize(n['type'])
        color = CATEGORY_COLOR[cat]
        x=n['_x']; y=n['_y']; h=n['_h']
        is_hl = (mat_name, n['name']) in HIGHLIGHTS
        if is_hl:
            # outer glow halo + golden border
            svg.append(f'<g filter="url(#glow)">'
                       f'<rect x="{x-4}" y="{y-4}" width="{NODE_W+8}" height="{h+8}" rx="10" fill="#ffd400" opacity="0.35"/>'
                       f'</g>')
            border = '#ffd400'; border_w = 4
        else:
            border = color; border_w = 2
        svg.append(f'<rect x="{x}" y="{y}" width="{NODE_W}" height="{h}" rx="6" fill="#3a3a3a" stroke="{border}" stroke-width="{border_w}"/>')
        svg.append(f'<rect x="{x}" y="{y}" width="{NODE_W}" height="{TITLE_H}" rx="6" fill="{color}"/>')
        title = html.escape(short_label(n))
        if len(title)>30: title = title[:28]+'…'
        svg.append(f'<text x="{x+8}" y="{y+15}" fill="#fff" font-weight="bold">{title}</text>')
        ty = y + TITLE_H + 12
        svg.append(f'<text x="{x+8}" y="{ty}" fill="#bbb" font-size="9">{html.escape(n["type"].replace("ShaderNode",""))}</text>')
        ty += LINE_H
        for line in n['_details']:
            svg.append(f'<text x="{x+8}" y="{ty}" fill="#ddd" font-size="10">{html.escape(line)}</text>')
            ty += LINE_H
        if is_hl:
            # callout label in gold under the node
            instruction = HIGHLIGHTS[(mat_name, n['name'])]
            cy = y + h + 16
            # background pill
            svg.append(f'<rect x="{x-4}" y="{cy-12}" width="{NODE_W+8}" height="36" rx="4" fill="#ffd400"/>')
            # break instruction into ~30-char lines
            words = instruction.split(' ')
            line=''; lines=[]
            for w in words:
                if len(line)+len(w)+1 > 32:
                    lines.append(line); line=w
                else:
                    line = w if not line else line+' '+w
            if line: lines.append(line)
            for i,ln in enumerate(lines[:2]):
                svg.append(f'<text x="{x+4}" y="{cy+i*13+1}" fill="#1a1a1a" font-size="10" font-weight="bold">{html.escape(ln)}</text>')

    # Legend
    lx = minx+20; ly = maxy-160
    svg.append(f'<rect x="{lx-10}" y="{ly-20}" width="190" height="150" fill="#1c1c1c" opacity="0.9" stroke="#555"/>')
    svg.append(f'<text x="{lx}" y="{ly-2}" fill="#eee" font-size="11">Node category color</text>')
    for i,(k,c) in enumerate(CATEGORY_COLOR.items()):
        svg.append(f'<rect x="{lx}" y="{ly+i*15}" width="12" height="12" fill="{c}"/>')
        svg.append(f'<text x="{lx+18}" y="{ly+i*15+10}" fill="#ddd" font-size="10">{k}</text>')

    svg.append('</svg>')
    with open(out_path,'w',encoding='utf-8') as f: f.write('\n'.join(svg))

def render_index(mat_files, out_path):
    # Count highlights per material name (strip the "[TAG] " prefix to match HIGHLIGHTS keys)
    items = []
    for name, fn in mat_files:
        bare = name.split('] ',1)[-1] if name.startswith('[') else name
        n_edits = sum(1 for (m,_) in HIGHLIGHTS if m == bare)
        badge = f' <span style="background:#ffd400;color:#000;padding:1px 6px;border-radius:8px;font-size:11px;font-weight:bold">{n_edits} edits</span>' if n_edits else ''
        items.append(f'<li><a href="{fn}">{html.escape(name)}</a>{badge}</li>')
    html_doc = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Shader diagrams</title>
<style>body{{font-family:Segoe UI,system-ui;background:#1c1c1c;color:#ddd;margin:24px}}a{{color:#7ac1ff}}h1{{margin-top:0}}ul{{line-height:1.8}}</style></head>
<body><h1>Shader node diagrams</h1>
<p>Click a material to view its node graph. Materials with a yellow <b>edits</b> badge contain glowing nodes that need tuning.</p>
<ul>{''.join(items)}</ul></body></html>"""
    with open(out_path,'w',encoding='utf-8') as f: f.write(html_doc)

def slug(s):
    return re.sub(r'[^A-Za-z0-9_.-]+','_', s)

def process(json_path, file_tag):
    txt = open(json_path,encoding='utf-8',errors='replace').read()
    txt = txt.replace('=====JSON_BEGIN=====','').replace('=====JSON_END=====','').strip()
    d = json.loads(txt)
    out_files = []
    for mname, mat in sorted(d['materials'].items()):
        if not mat or not mat.get('nodes'): continue
        fn = f"{file_tag}__{slug(mname)}.svg"
        render_material(mname, mat, os.path.join(OUT_DIR, fn))
        out_files.append((mname, fn))
    return out_files

if __name__ == '__main__':
    all_items = []
    files = [
        ('LO_086', 'C:/Users/14047/Documents/VS Code Scripts/blender-render-pipeline/workspace/project/notes/_pos_LO_086.json'),
        ('TUT',    'C:/Users/14047/Documents/VS Code Scripts/blender-render-pipeline/workspace/project/notes/_pos_TUT.json'),
        ('MANGA',  'C:/Users/14047/Documents/VS Code Scripts/blender-render-pipeline/workspace/project/notes/_pos_MANGA.json'),
    ]
    for tag, path in files:
        items = process(path, tag)
        all_items += [(f'[{tag}] {n}', f) for n,f in items]
    render_index(all_items, os.path.join(OUT_DIR,'index.html'))
    print(f"Wrote {len(all_items)} SVGs to {OUT_DIR}")
