export class SDFGElement {
    // Parent ID is the state ID, if relevant
    constructor(elem, elem_id, sdfg, parent_id = null) {
        this.data = elem;
        this.id = elem_id;
        this.parent_id = parent_id;
        this.sdfg = sdfg;
        this.connectors = [];
        this.set_layout();
    }

    set_layout() {
        // dagre does not work well with properties, only fields
        this.width = this.data.layout.width;
        this.height = this.data.layout.height;
    }

    draw(ctx, highlighted, mousepos) {}

    label() {
        return this.data.label;
    }

    long_label() {
        return this.label();
    }

    // Produces HTML for a hover-tooltip
    tooltip() {
        return null;
    }

    topleft() {
        return {x: this.x - this.width / 2, y: this.y - this.height / 2};
    }

    strokeStyle(highlighted) {
        if(highlighted === 'select') {
            return "red";
        } else if(highlighted === 'hover') {
            return "green";
        } else {
            return "black";
        }
    }
}

export class State extends SDFGElement {
    draw(ctx, highlighted, mousepos) {
        let topleft = this.topleft();

        ctx.fillStyle = "#deebf7";
        ctx.fillRect(topleft.x, topleft.y, this.width, this.height);
        ctx.fillStyle = "#000000";

        ctx.fillText(this.label(), topleft.x, topleft.y + LINEHEIGHT);

        // If this state is selected or hovered
        if (highlighted) {
            ctx.strokeStyle = this.strokeStyle(highlighted);
            ctx.stroke();
            ctx.strokeStyle = "black";
        }
    }

    label() {
        return this.data.state.label;
    }
}

export class Node extends SDFGElement {
    draw(ctx, highlighted, mousepos) {
        let topleft = this.topleft();
        ctx.fillStyle = "white";
        ctx.fillRect(topleft.x, topleft.y, this.width, this.height);
        ctx.strokeStyle = this.strokeStyle(highlighted);
        ctx.strokeRect(topleft.x, topleft.y, this.width, this.height);
        ctx.fillStyle = "black";
        let textw = ctx.measureText(this.label()).width;
        ctx.fillText(this.label(), this.x - textw/2, this.y + LINEHEIGHT/4);
    }

    label() {
        return this.data.node.label;
    }

    set_layout() {
        this.width = this.data.node.attributes.layout.width;
        this.height = this.data.node.attributes.layout.height;
    }
}

export class Edge extends SDFGElement {
    draw(ctx, highlighted, mousepos) {
        let edge = this.data;

        ctx.beginPath();
        ctx.moveTo(edge.points[0].x, edge.points[0].y);

        let i;
        for (i = 1; i < edge.points.length - 2; i++) {
            let xm = (edge.points[i].x + edge.points[i + 1].x) / 2.0;
            let ym = (edge.points[i].y + edge.points[i + 1].y) / 2.0;
            ctx.quadraticCurveTo(edge.points[i].x, edge.points[i].y, xm, ym);
        }
        ctx.quadraticCurveTo(edge.points[i].x, edge.points[i].y,
                             edge.points[i+1].x, edge.points[i+1].y);

        ctx.strokeStyle = this.strokeStyle(highlighted);
        ctx.fillStyle = this.strokeStyle(highlighted);

        ctx.stroke();

        if (edge.points.length < 2)
            return;
        drawArrow(ctx, edge.points[edge.points.length - 2], edge.points[edge.points.length - 1], 3);

        ctx.fillStyle = "black";
        ctx.strokeStyle = "black";
    }

    tooltip() {
        return this.label();
    }

    set_layout() {
        this.width = this.data.width;
        this.height = this.data.height;
    }
}

export class Connector extends SDFGElement {
    draw(ctx, highlighted, mousepos) {
        let topleft = this.topleft();
        ctx.beginPath();
        drawEllipse(ctx, topleft.x, topleft.y, this.width, this.height);
        ctx.closePath();
        ctx.strokeStyle = this.strokeStyle(highlighted);
        ctx.stroke();
        ctx.fillStyle = "#f0fdff";
        ctx.fill();
        ctx.fillStyle = "black";
        ctx.strokeStyle = "black";
    }

    set_layout() { }

    tooltip() {
        return this.label();
    }
}

export class AccessNode extends Node {
    draw(ctx, highlighted, mousepos) {
        let topleft = this.topleft();
        ctx.beginPath();
        drawEllipse(ctx, topleft.x, topleft.y, this.width, this.height);
        ctx.closePath();
        ctx.strokeStyle = this.strokeStyle(highlighted);

        let nodedesc = this.sdfg.attributes._arrays[this.data.node.attributes.data];
        // Streams have dashed edges
        if (nodedesc.type === "Stream") {
            ctx.setLineDash([5, 3]);
        } else {
            ctx.setLineDash([1, 0]);
        }

        if (nodedesc.attributes.transient === false) {
            ctx.lineWidth = 3.0;
        } else {
            ctx.lineWidth = 1.0;
        }


        ctx.stroke();
        ctx.lineWidth = 1.0;
        ctx.setLineDash([1, 0]);
        ctx.fillStyle = "white";
        ctx.fill();
        ctx.fillStyle = "black";
        var textmetrics = ctx.measureText(this.label());
        ctx.fillText(this.label(), this.x - textmetrics.width / 2.0, this.y + LINEHEIGHT / 4.0);
    }
}

export class ScopeNode extends Node {
    draw(ctx, highlighted, mousepos) {
        if (this.data.node.attributes.is_collapsed) {
            drawHexagon(ctx, this.x, this.y, this.width, this.height);
        } else {
            let topleft = this.topleft();
            drawTrapezoid(ctx, this.topleft(), this, this.scopeend());
        }
        ctx.strokeStyle = this.strokeStyle(highlighted);

        // Consume scopes have dashed edges
        if (this.data.node.type.startsWith("Consume"))
            ctx.setLineDash([5, 3]);
        else
            ctx.setLineDash([1, 0]);


        ctx.stroke();
        ctx.setLineDash([1, 0]);
        ctx.fillStyle = "white";
        ctx.fill();
        ctx.fillStyle = "black";
        var textmetrics = ctx.measureText(this.label());
        ctx.fillText(this.label(), this.x - textmetrics.width / 2.0, this.y + LINEHEIGHT / 2.0);
    }
}

export class EntryNode extends ScopeNode {
    scopeend() { return false; }
}

export class ExitNode extends ScopeNode {
    scopeend() { return true; }
}

export class MapEntry extends EntryNode { stroketype(ctx) { ctx.setLineDash([1, 0]); } }
export class MapExit extends ExitNode {  stroketype(ctx) { ctx.setLineDash([1, 0]); } }
export class ConsumeEntry extends EntryNode {  stroketype(ctx) { ctx.setLineDash([5, 3]); } }
export class ConsumeExit extends ExitNode {  stroketype(ctx) { ctx.setLineDash([5, 3]); } }

export class Tasklet extends Node {
    draw(ctx, highlighted, mousepos) {
        let topleft = this.topleft();
        let octseg = this.height / 3.0;
        ctx.beginPath();
        ctx.moveTo(topleft.x, topleft.y + octseg);
        ctx.lineTo(topleft.x + octseg, topleft.y);
        ctx.lineTo(topleft.x + this.width - octseg, topleft.y);
        ctx.lineTo(topleft.x + this.width, topleft.y + octseg);
        ctx.lineTo(topleft.x + this.width, topleft.y + 2 * octseg);
        ctx.lineTo(topleft.x + this.width - octseg, topleft.y + this.height);
        ctx.lineTo(topleft.x + octseg, topleft.y + this.height);
        ctx.lineTo(topleft.x, topleft.y + 2 * octseg);
        ctx.lineTo(topleft.x, topleft.y + 1 * octseg);
        ctx.closePath();
        ctx.strokeStyle = this.strokeStyle(highlighted);
        ctx.stroke();
        ctx.fillStyle = "white";
        ctx.fill();
        ctx.fillStyle = "black";
        let textmetrics = ctx.measureText(this.label());
        ctx.fillText(this.label(), this.x - textmetrics.width / 2.0, this.y + LINEHEIGHT / 2.0);
    }
}

export class Reduce extends Node {
    draw(ctx, highlighted, mousepos) {
        let topleft = this.topleft();
        ctx.beginPath();
        ctx.moveTo(topleft.x, topleft.y);
        ctx.lineTo(topleft.x + this.width / 2, topleft.y + this.height);
        ctx.lineTo(topleft.x + this.width, topleft.y);
        ctx.lineTo(topleft.x, topleft.y);
        ctx.closePath();
        ctx.strokeStyle = this.strokeStyle(highlighted);
        ctx.stroke();
        ctx.fillStyle = "white";
        ctx.fill();
        ctx.fillStyle = "black";
        var textmetrics = ctx.measureText(this.label());
        ctx.fillText(this.label(), this.x - textmetrics.width / 2.0, this.y - this.height / 4.0 + LINEHEIGHT / 2.0);    }
}

export class NestedSDFG extends Node {
    draw(ctx, highlighted, mousepos) {
        // Draw square around nested SDFG
        super.draw(ctx, highlighted, mousepos);

        // Draw nested graph
        draw_sdfg(ctx, this.data.graph, null, mousepos);
    }

    label() { return ""; }
}

//////////////////////////////////////////////////////

// Draw an entire SDFG
function draw_sdfg(ctx, sdfg_dagre, visible_rect, mousepos) {
    // Render state machine
    let g = sdfg_dagre;
    g.nodes().forEach( v => { g.node(v).draw(ctx, false, mousepos); });
    g.edges().forEach( e => { g.edge(e).draw(ctx, false, mousepos); });

    // TODO: Render each visible state's contents
    g.nodes().forEach( v => {
        let node = g.node(v);
        let ng = node.data.graph;
        let layout = node.data.state.attributes.layout;
        
        if (!node.data.state.attributes.is_collapsed/* && isBBoverlapped(curx, cury, curw, curh, layout)*/)
        {
            ng.nodes().forEach(v => {
                let n = ng.node(v);
                n.draw(ctx, false, mousepos);
                n.connectors.forEach(c => { c.draw(ctx, false, mousepos); });
            });
            ng.edges().forEach(e => {
                ng.edge(e).draw(ctx, false, mousepos);
            });
        }
    });
}

// Translate an SDFG by a given offset
function offset_sdfg(sdfg, sdfg_graph, offset) {
    sdfg.nodes.forEach((state, id) => {
        let g = sdfg_graph.node(id);
        g.x += offset.x;
        g.y += offset.y;
        offset_state(state, g, offset);
    });
    sdfg.edges.forEach((e, id) => {
        let edge = sdfg_graph.edge(e.src, e.dst, eid);
        edge.x += offset.x;
        edge.y += offset.y;
        edge.data.points.forEach((p) => {
            p.x += offset.x;
            p.y += offset.y;
        });
    });
}

// Translate nodes, edges, and connectors in a given SDFG state by an offset
function offset_state(state, state_graph, offset) {
    state.nodes.forEach((n, nid) => {
        let node = state_graph.data.graph.node(nid);
        node.x += offset.x;
        node.y += offset.y;
        node.connectors.forEach(c => {
            c.x += offset.x;
            c.y += offset.y;
        });


        if (node.data.node.type === 'NestedSDFG')
            offset_sdfg(node.data.node.attributes.sdfg, node.data.graph, offset);
    });
    state.edges.forEach((e, eid) => {
        let edge = state_graph.data.graph.edge(e.src, e.dst, eid);
        edge.x += offset.x;
        edge.y += offset.y;
        edge.data.points.forEach((p) => {
            p.x += offset.x;
            p.y += offset.y;
        });
    });
}


///////////////////////////////////////////////////////

function drawHexagon(ctx, x, y, w, h, offset) {
    let topleft = {x: x - w / 2.0, y: y - h / 2.0};
    let hexseg = h / 3.0;
    ctx.beginPath();
    ctx.moveTo(topleft.x, y);
    ctx.lineTo(topleft.x + hexseg, topleft.y);
    ctx.lineTo(topleft.x + w - hexseg, topleft.y);
    ctx.lineTo(topleft.x + w, y);
    ctx.lineTo(topleft.x + w - hexseg, topleft.y + h);
    ctx.lineTo(topleft.x + hexseg, topleft.y + h);
    ctx.lineTo(topleft.x, y);
    ctx.closePath();
}

// Adapted from https://stackoverflow.com/a/2173084/6489142
function drawEllipse(ctx, x, y, w, h) {
    var kappa = .5522848,
    ox = (w / 2) * kappa, // control point offset horizontal
    oy = (h / 2) * kappa, // control point offset vertical
    xe = x + w,           // x-end
    ye = y + h,           // y-end
    xm = x + w / 2,       // x-middle
    ym = y + h / 2;       // y-middle

    ctx.moveTo(x, ym);
    ctx.bezierCurveTo(x, ym - oy, xm - ox, y, xm, y);
    ctx.bezierCurveTo(xm + ox, y, xe, ym - oy, xe, ym);
    ctx.bezierCurveTo(xe, ym + oy, xm + ox, ye, xm, ye);
    ctx.bezierCurveTo(xm - ox, ye, x, ym + oy, x, ym);
}

function drawArrow(ctx, p1, p2, size, offset) {
    ctx.save();
    // Rotate the context to point along the path
    let dx = p2.x - p1.x;
    let dy = p2.y - p1.y;
    ctx.translate(p2.x, p2.y);
    ctx.rotate(Math.atan2(dy, dx));

    // arrowhead
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(-2 * size, -size);
    ctx.lineTo(-2 * size, size);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
}

function drawTrapezoid(ctx, topleft, node, inverted=false) {
    ctx.beginPath();
    if (inverted) {
        ctx.moveTo(topleft.x, topleft.y);
        ctx.lineTo(topleft.x + node.width, topleft.y);
        ctx.lineTo(topleft.x + node.width - node.height, topleft.y + node.height);
        ctx.lineTo(topleft.x + node.height, topleft.y + node.height);
        ctx.lineTo(topleft.x, topleft.y);
    } else {
        ctx.moveTo(topleft.x, topleft.y + node.height);
        ctx.lineTo(topleft.x + node.width, topleft.y + node.height);
        ctx.lineTo(topleft.x + node.width - node.height, topleft.y);
        ctx.lineTo(topleft.x + node.height, topleft.y);
        ctx.lineTo(topleft.x, topleft.y + node.height);
    }
    ctx.closePath();
}

export {draw_sdfg, offset_sdfg, offset_state};
