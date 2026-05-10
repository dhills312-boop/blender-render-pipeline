import bpy, sys, json

def dump_node_tree(nt):
    if nt is None: return None
    out_nodes = []
    for n in nt.nodes:
        info = {
            "name": n.name, "label": getattr(n, "label", ""),
            "type": n.bl_idname,
            "x": n.location.x, "y": n.location.y,
            "w": n.width, "h": n.height,
        }
        if n.bl_idname == "ShaderNodeTexWave":
            info["wave_type"]=n.wave_type; info["bands_direction"]=getattr(n,"bands_direction","")
            info["wave_profile"]=n.wave_profile
        elif n.bl_idname == "ShaderNodeTexVoronoi":
            info["feature"]=n.feature; info["distance"]=n.distance; info["dim"]=n.voronoi_dimensions
        elif n.bl_idname == "ShaderNodeValToRGB":
            r=n.color_ramp; info["interpolation"]=r.interpolation
            info["elements"]=[{"pos":e.position,"color":list(e.color)} for e in r.elements]
        elif n.bl_idname in ("ShaderNodeMixRGB","ShaderNodeMix"):
            info["blend_type"]=getattr(n,"blend_type","")
        elif n.bl_idname == "ShaderNodeMath":
            info["operation"]=n.operation
        # input snapshot for any node
        for inp in n.inputs:
            try:
                if hasattr(inp,"default_value") and not inp.is_linked:
                    v = inp.default_value
                    if hasattr(v,"__len__"): v = list(v)
                    info[f"in:{inp.name}"]=v
            except: pass
        out_nodes.append(info)
    links=[]
    for l in nt.links:
        links.append({
            "from_node": l.from_node.name, "from_sock": l.from_socket.name,
            "to_node": l.to_node.name, "to_sock": l.to_socket.name,
        })
    return {"nodes": out_nodes, "links": links}

result={"materials":{},"groups":{}}
for mat in bpy.data.materials:
    if mat.use_nodes and mat.node_tree:
        result["materials"][mat.name]=dump_node_tree(mat.node_tree)
for g in bpy.data.node_groups:
    result["groups"][g.name]=dump_node_tree(g)

print("=====JSON_BEGIN=====")
print(json.dumps(result, default=str))
print("=====JSON_END=====")
