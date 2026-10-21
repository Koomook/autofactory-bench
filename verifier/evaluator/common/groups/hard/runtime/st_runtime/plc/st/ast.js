"use strict";
/** Structured Text AST. Ladder also compiles to this AST and uses the same interpreter. */
Object.defineProperty(exports, "__esModule", { value: true });
exports.collectRefs = collectRefs;
exports.walkStmts = walkStmts;
exports.collectWrites = collectWrites;
exports.collectReads = collectReads;
/** Collect referenced variable names from an expression for cross-reference and unused-symbol checks. */
function collectRefs(e, out = new Set()) {
    switch (e.k) {
        case 'var':
            out.add(e.name.toUpperCase());
            break;
        case 'member':
            collectRefs(e.obj, out);
            break;
        case 'index':
            collectRefs(e.obj, out);
            collectRefs(e.idx, out);
            break;
        case 'un':
            collectRefs(e.e, out);
            break;
        case 'bin':
            collectRefs(e.l, out);
            collectRefs(e.r, out);
            break;
        case 'call':
            out.add(e.name.toUpperCase());
            e.args.forEach((a) => collectRefs(a.value, out));
            break;
    }
    return out;
}
/** Walk statements; do not descend into a branch when visit returns false. */
function walkStmts(body, visit) {
    for (const s of body) {
        if (visit(s) === false)
            continue;
        switch (s.k) {
            case 'if':
                s.branches.forEach((b) => walkStmts(b.body, visit));
                if (s.orElse)
                    walkStmts(s.orElse, visit);
                break;
            case 'case':
                s.cases.forEach((b) => walkStmts(b.body, visit));
                if (s.orElse)
                    walkStmts(s.orElse, visit);
                break;
            case 'for':
            case 'while':
            case 'repeat':
                walkStmts(s.body, visit);
                break;
        }
    }
}
/** Collect variable names written on the left side of assignments. */
function collectWrites(body) {
    const out = new Set();
    walkStmts(body, (s) => {
        if (s.k === 'assign') {
            let t = s.target;
            while (t.k === 'member' || t.k === 'index')
                t = t.obj;
            if (t.k === 'var')
                out.add(t.name.toUpperCase());
        }
        else if (s.k === 'call') {
            // An FB call's output argument (Q => DONE) is also a write.
            for (const a of s.args) {
                if (a.isOutput && a.value.k === 'var')
                    out.add(a.value.name.toUpperCase());
            }
        }
    });
    return out;
}
/** Collect symbols read by this program. */
function collectReads(body) {
    const out = new Set();
    walkStmts(body, (s) => {
        switch (s.k) {
            case 'assign':
                collectRefs(s.value, out);
                if (s.target.k === 'index')
                    collectRefs(s.target.idx, out);
                break;
            case 'call':
                s.args.forEach((a) => { if (!a.isOutput)
                    collectRefs(a.value, out); });
                break;
            case 'if':
                s.branches.forEach((b) => collectRefs(b.cond, out));
                break;
            case 'case':
                collectRefs(s.selector, out);
                break;
            case 'for':
                collectRefs(s.from, out);
                collectRefs(s.to, out);
                if (s.by)
                    collectRefs(s.by, out);
                break;
            case 'while':
                collectRefs(s.cond, out);
                break;
            case 'repeat':
                collectRefs(s.until, out);
                break;
        }
    });
    return out;
}
