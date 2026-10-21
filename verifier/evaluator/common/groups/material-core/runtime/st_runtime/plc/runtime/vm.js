"use strict";
/**

 *



 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.PlcRuntime = exports.Scope = void 0;
const types_1 = require("../types");
const fb_1 = require("./fb");
const functions_1 = require("./functions");

const WATCHDOG_ITERATIONS = 200000;
class Scope {
    constructor(parent, label = '') {
        this.parent = parent;
        this.label = label;
        this.vars = new Map();
    }
    lookup(key) {
        return this.vars.get(key) ?? this.parent?.lookup(key);
    }
    declare(decl) {
        const sym = {
            decl,
            value: decl.initial ?? (0, types_1.defaultValue)(decl.type),
        };
        if (decl.dim) {
            const [lo, hi] = decl.dim;
            sym.array = new Array(Math.max(0, hi - lo + 1)).fill(decl.initial ?? (0, types_1.defaultValue)(decl.type));
        }
        if (decl.fbType) {
            const b = fb_1.BUILTIN_FBS[decl.fbType];
            sym.fb = { type: decl.fbType, builtin: b ? b.init() : undefined };
        }
        this.vars.set(decl.key, sym);
        return sym;
    }
}
exports.Scope = Scope;
const asBool = (v) => typeof v === 'boolean' ? v : typeof v === 'number' ? v !== 0 : v.length > 0;
const asNum = (v) => typeof v === 'boolean' ? (v ? 1 : 0) : typeof v === 'number' ? v : Number(v) || 0;
class PlcRuntime {
    constructor(program) {
        this.program = program;
        this.globals = new Scope(undefined, 'GLOBAL');

        this.programs = [];

        this.fbDefs = new Map();
        this.funcDefs = new Map();
        this.scanCount = 0;

        this.elapsed = 0;

        this.fault = null;
        this.iterations = 0;
        this.dt = 0;
        this.build();
    }
    build() {
        for (const g of this.program.globals)
            this.globals.declare(g);
        for (const pou of this.program.pous) {
            if (pou.kind === 'FUNCTION_BLOCK') {
                this.fbDefs.set((0, types_1.normKey)(pou.name), pou);
            }
            else if (pou.kind === 'FUNCTION') {
                this.funcDefs.set((0, types_1.normKey)(pou.name), pou);
            }
        }

        for (const pou of this.program.pous) {
            if (pou.kind !== 'PROGRAM')
                continue;
            const scope = new Scope(this.globals, pou.name);
            for (const v of pou.vars)
                this.declareIn(scope, v);
            this.programs.push({ pou, scope });
        }
    }
    declareIn(scope, decl) {
        const sym = scope.declare(decl);

        if (decl.fbType && !fb_1.BUILTIN_FBS[decl.fbType]) {
            const def = this.fbDefs.get(decl.fbType);
            if (def) {
                const inner = new Scope(this.globals, `${decl.name}:${def.name}`);
                for (const v of def.vars)
                    this.declareIn(inner, v);
                sym.fb = { type: decl.fbType, userScope: inner };
            }
        }
        return sym;
    }

    reset() {
        this.globals = new Scope(undefined, 'GLOBAL');
        this.programs = [];
        this.fbDefs.clear();
        this.funcDefs.clear();
        this.scanCount = 0;
        this.elapsed = 0;
        this.fault = null;
        this.build();
    }


    findSym(name) {
        const key = (0, types_1.normKey)(name);
        const g = this.globals.vars.get(key);
        if (g)
            return g;
        for (const p of this.programs) {
            const s = p.scope.vars.get(key);
            if (s)
                return s;
        }
        return undefined;
    }
    get(name) {
        const s = this.findSym(name);
        if (!s)
            return undefined;
        return s.forced ?? s.value;
    }
    set(name, value) {
        const s = this.findSym(name);
        if (!s)
            return false;
        s.value = (0, types_1.coerce)(value, s.decl.type);
        return true;
    }
    force(name, value) {
        const s = this.findSym(name);
        if (!s)
            return;
        s.forced = value === undefined ? undefined : (0, types_1.coerce)(value, s.decl.type);
    }

    listTags() {
        const out = [];
        for (const [key, s] of this.globals.vars) {
            if (s.decl.fbType)
                continue;
            out.push({ name: s.decl.name, key, decl: s.decl, pou: 'GLOBAL' });
        }
        for (const p of this.programs) {
            for (const [key, s] of p.scope.vars) {
                if (s.decl.fbType)
                    continue;
                if (out.some((t) => t.key === key))
                    continue;
                out.push({ name: s.decl.name, key, decl: s.decl, pou: p.pou.name });
            }
        }
        return out;
    }

    listFbInstances() {
        const out = [];
        const visit = (scope) => {
            for (const s of scope.vars.values()) {
                if (s.fb?.builtin)
                    out.push({ name: s.decl.name, type: s.fb.type, state: s.fb.builtin });
            }
        };
        visit(this.globals);
        this.programs.forEach((p) => visit(p.scope));
        return out;
    }

    snapshot() {
        const out = {};
        for (const t of this.listTags()) {
            const s = this.findSym(t.key);
            if (s)
                out[t.key] = s.forced ?? s.value;
        }
        return out;
    }


    scan(dt) {
        this.dt = Math.max(0, dt);
        this.iterations = 0;
        this.fault = null;
        try {
            for (const { pou, scope } of this.programs) {
                this.execBlock(pou.body, scope);
            }
        }
        catch (e) {
            this.fault = e instanceof types_1.PlcError ? e : new types_1.PlcError(String(e?.message ?? e));
        }
        this.scanCount++;
        this.elapsed += this.dt;
    }

    tick(pos) {
        if (++this.iterations > WATCHDOG_ITERATIONS) {
            throw new types_1.PlcError(`Watchdog: exceeded ${WATCHDOG_ITERATIONS} iterations in one scan; check for a nonterminating loop.`, pos?.line ?? 0, pos?.col ?? 0);
        }
    }
    execBlock(body, scope) {
        for (const s of body) {
            const f = this.execStmt(s, scope);
            if (f !== 0 /* Flow.Normal */)
                return f;
        }
        return 0 /* Flow.Normal */;
    }
    execStmt(s, scope) {
        this.tick(s.pos);
        switch (s.k) {
            case 'assign':
                this.assign(s.target, this.evalExpr(s.value, scope), scope);
                return 0 /* Flow.Normal */;
            case 'call':
                this.invoke(s.name, s.args, scope, s.pos);
                return 0 /* Flow.Normal */;
            case 'if': {
                for (const br of s.branches) {
                    if (asBool(this.evalExpr(br.cond, scope)))
                        return this.execBlock(br.body, scope);
                }
                return s.orElse ? this.execBlock(s.orElse, scope) : 0 /* Flow.Normal */;
            }
            case 'case': {
                const v = asNum(this.evalExpr(s.selector, scope));
                for (const br of s.cases) {
                    if (br.labels.some((l) => v >= l.lo && v <= l.hi))
                        return this.execBlock(br.body, scope);
                }
                return s.orElse ? this.execBlock(s.orElse, scope) : 0 /* Flow.Normal */;
            }
            case 'for': {
                const key = (0, types_1.normKey)(s.varName);
                let sym = scope.lookup(key);
                if (!sym) {

                    sym = scope.declare({ name: s.varName, key, type: 'INT', scope: 'temp' });
                }
                const from = asNum(this.evalExpr(s.from, scope));
                const to = asNum(this.evalExpr(s.to, scope));
                const by = s.by ? asNum(this.evalExpr(s.by, scope)) : 1;
                if (by === 0)
                    throw new types_1.PlcError('FOR loop cannot terminate when BY is zero', s.pos.line, s.pos.col);
                for (let i = from; by > 0 ? i <= to : i >= to; i += by) {
                    this.tick(s.pos);
                    sym.value = i;
                    const f = this.execBlock(s.body, scope);
                    if (f === 1 /* Flow.Exit */)
                        break;
                    if (f === 3 /* Flow.Return */)
                        return f;
                }
                return 0 /* Flow.Normal */;
            }
            case 'while': {
                while (asBool(this.evalExpr(s.cond, scope))) {
                    this.tick(s.pos);
                    const f = this.execBlock(s.body, scope);
                    if (f === 1 /* Flow.Exit */)
                        break;
                    if (f === 3 /* Flow.Return */)
                        return f;
                }
                return 0 /* Flow.Normal */;
            }
            case 'repeat': {
                for (;;) {
                    this.tick(s.pos);
                    const f = this.execBlock(s.body, scope);
                    if (f === 1 /* Flow.Exit */)
                        break;
                    if (f === 3 /* Flow.Return */)
                        return f;
                    if (asBool(this.evalExpr(s.until, scope)))
                        break;
                }
                return 0 /* Flow.Normal */;
            }
            case 'exit':
                return 1 /* Flow.Exit */;
            case 'continue':
                return 2 /* Flow.Continue */;
            case 'return':
                return 3 /* Flow.Return */;
        }
    }

    assign(target, value, scope) {
        if (target.k === 'var') {
            const sym = this.need(target.name, scope, target.pos);
            sym.value = (0, types_1.coerce)(value, sym.decl.type);
            return;
        }
        if (target.k === 'index') {
            if (target.obj.k !== 'var') {
                throw new types_1.PlcError('Invalid left-hand side for array assignment', target.pos.line, target.pos.col);
            }
            const sym = this.need(target.obj.name, scope, target.pos);
            if (!sym.array || !sym.decl.dim) {
                throw new types_1.PlcError(`${target.obj.name} is not an array`, target.pos.line, target.pos.col);
            }
            const idx = asNum(this.evalExpr(target.idx, scope)) - sym.decl.dim[0];
            if (idx < 0 || idx >= sym.array.length) {
                throw new types_1.PlcError(`Array index out of bounds: ${target.obj.name}[${idx + sym.decl.dim[0]}]`, target.pos.line, target.pos.col);
            }
            sym.array[idx] = (0, types_1.coerce)(value, sym.decl.type);
            return;
        }
        if (target.k === 'member') {
            if (target.obj.k !== 'var') {
                throw new types_1.PlcError('Invalid left-hand side for member assignment', target.pos.line, target.pos.col);
            }
            const sym = this.need(target.obj.name, scope, target.pos);
            if (!sym.fb) {
                throw new types_1.PlcError(`${target.obj.name} is not a function-block instance`, target.pos.line, target.pos.col);
            }
            const prop = target.prop.toUpperCase();
            if (sym.fb.builtin) {
                sym.fb.builtin.in[prop] = value;
            }
            else if (sym.fb.userScope) {
                const inner = sym.fb.userScope.vars.get(prop);
                if (!inner) {
                    throw new types_1.PlcError(`${sym.fb.type} has no member ${target.prop}`, target.pos.line, target.pos.col);
                }
                inner.value = (0, types_1.coerce)(value, inner.decl.type);
            }
            return;
        }
        throw new types_1.PlcError('Left-hand side is not assignable', target.pos.line, target.pos.col);
    }
    need(name, scope, pos) {
        const sym = scope.lookup((0, types_1.normKey)(name));
        if (!sym) {
            throw new types_1.PlcError(`Undeclared variable: ${name}; add it to a VAR block`, pos.line, pos.col, name.length);
        }
        return sym;
    }
    evalExpr(e, scope) {
        switch (e.k) {
            case 'lit':
                return e.value;
            case 'var': {
                const sym = this.need(e.name, scope, e.pos);
                return sym.forced ?? sym.value;
            }
            case 'member': {
                if (e.obj.k !== 'var') {
                    throw new types_1.PlcError('Invalid member access target', e.pos.line, e.pos.col);
                }
                const sym = this.need(e.obj.name, scope, e.pos);
                const prop = e.prop.toUpperCase();
                if (!sym.fb) {
                    throw new types_1.PlcError(`${e.obj.name} is not a function-block instance`, e.pos.line, e.pos.col);
                }
                if (sym.fb.builtin) {
                    const st = sym.fb.builtin;
                    if (prop in st.out)
                        return st.out[prop];
                    if (prop in st.in)
                        return st.in[prop];
                    throw new types_1.PlcError(`${sym.fb.type} has no output ${e.prop}`, e.pos.line, e.pos.col);
                }
                const inner = sym.fb.userScope?.vars.get(prop);
                if (!inner)
                    throw new types_1.PlcError(`${sym.fb.type} has no member ${e.prop}`, e.pos.line, e.pos.col);
                return inner.value;
            }
            case 'index': {
                if (e.obj.k !== 'var')
                    throw new types_1.PlcError('Invalid array access target', e.pos.line, e.pos.col);
                const sym = this.need(e.obj.name, scope, e.pos);
                if (!sym.array || !sym.decl.dim) {
                    throw new types_1.PlcError(`${e.obj.name} is not an array`, e.pos.line, e.pos.col);
                }
                const idx = asNum(this.evalExpr(e.idx, scope)) - sym.decl.dim[0];
                if (idx < 0 || idx >= sym.array.length) {
                    throw new types_1.PlcError(`Array index out of bounds: ${e.obj.name}[${idx + sym.decl.dim[0]}]`, e.pos.line, e.pos.col);
                }
                return sym.array[idx];
            }
            case 'un': {
                const v = this.evalExpr(e.e, scope);
                if (e.op === 'NOT')
                    return typeof v === 'number' ? ~v & 0xffff : !asBool(v);
                if (e.op === '-')
                    return -asNum(v);
                return asNum(v);
            }
            case 'bin':
                return this.evalBin(e, scope);
            case 'call':
                return this.invoke(e.name, e.args, scope, e.pos);
        }
    }
    isIntExpr(e, scope) {
        // EF fix G-INTDIV: static integer typing used by integer division.
        const INT_TYPES = new Set(['SINT', 'INT', 'DINT', 'LINT', 'USINT', 'UINT', 'UDINT', 'ULINT', 'BYTE', 'WORD', 'DWORD', 'LWORD']);
        const INT_FUNCS = new Set(['INT', 'DINT', 'SINT', 'WORD', 'DWORD', 'BYTE', 'TRUNC', 'REAL_TO_INT', 'TIME_TO_INT', 'BOOL_TO_INT']);
        switch (e.k) {
            case 'lit':
                return e.type === 'INT';
            case 'var':
            case 'index': {
                const name = e.k === 'var' ? e.name : (e.obj && e.obj.name);
                const sym = name ? scope.lookup((0, types_1.normKey)(name)) : undefined;
                return !!(sym && !sym.fb && sym.decl && INT_TYPES.has(String(sym.decl.type).toUpperCase()));
            }
            case 'un':
                return e.op !== 'NOT' && this.isIntExpr(e.e, scope);
            case 'bin':
                return ['+', '-', '*', '/', 'MOD'].includes(e.op) && this.isIntExpr(e.l, scope) && this.isIntExpr(e.r, scope);
            case 'call': {
                const key = String(e.name).toUpperCase();
                if (INT_FUNCS.has(key))
                    return true;
                if (['ABS', 'MIN', 'MAX', 'LIMIT'].includes(key))
                    return e.args.every((a) => this.isIntExpr(a.value, scope));
                return false;
            }
        }
        return false;
    }
    evalBin(e, scope) {

        if (e.op === 'AND') {
            const l = this.evalExpr(e.l, scope);
            if (typeof l === 'number')
                return l & asNum(this.evalExpr(e.r, scope));
            if (!asBool(l))
                return false;
            return asBool(this.evalExpr(e.r, scope));
        }
        if (e.op === 'OR') {
            const l = this.evalExpr(e.l, scope);
            if (typeof l === 'number')
                return l | asNum(this.evalExpr(e.r, scope));
            if (asBool(l))
                return true;
            return asBool(this.evalExpr(e.r, scope));
        }
        const l = this.evalExpr(e.l, scope);
        const r = this.evalExpr(e.r, scope);
        switch (e.op) {
            case 'XOR':
                return typeof l === 'number' && typeof r === 'number' ? l ^ r : asBool(l) !== asBool(r);
            case '=':
                return typeof l === 'string' || typeof r === 'string' ? String(l) === String(r) : asNum(l) === asNum(r);
            case '<>':
                return typeof l === 'string' || typeof r === 'string' ? String(l) !== String(r) : asNum(l) !== asNum(r);
            case '<': return asNum(l) < asNum(r);
            case '>': return asNum(l) > asNum(r);
            case '<=': return asNum(l) <= asNum(r);
            case '>=': return asNum(l) >= asNum(r);
            case '+':
                return typeof l === 'string' || typeof r === 'string' ? String(l) + String(r) : asNum(l) + asNum(r);
            case '-': return asNum(l) - asNum(r);
            case '*': return asNum(l) * asNum(r);
            case '/': {
                const d = asNum(r);

                if (d === 0)
                    throw new types_1.PlcError('Division by zero', e.pos.line, e.pos.col);
                // EF fix G-INTDIV: integer operands divide with truncation toward zero (IEC 61131-3).
                if (this.isIntExpr(e.l, scope) && this.isIntExpr(e.r, scope))
                    return Math.trunc(asNum(l) / d);
                return asNum(l) / d;
            }
            case 'MOD': {
                const d = asNum(r);
                if (d === 0)
                    throw new types_1.PlcError('MOD divisor is zero', e.pos.line, e.pos.col);
                return asNum(l) % d;
            }
            case '**': return Math.pow(asNum(l), asNum(r));
        }
    }
    /**




     */
    invoke(name, args, scope, pos) {
        const key = (0, types_1.normKey)(name);
        const sym = scope.lookup(key);
        if (sym?.fb)
            return this.callFb(sym, args, scope, pos);
        const fn = this.funcDefs.get(key);
        if (fn)
            return this.callUserFunction(fn, args, scope, pos);
        const std = functions_1.STD_FUNCTIONS[key];
        if (std) {
            const vals = args.map((a) => this.evalExpr(a.value, scope));
            return std(vals);
        }
        throw new types_1.PlcError(`Unknown call: ${name}; check that the function-block instance is declared in VAR`, pos.line, pos.col, name.length);
    }
    callFb(sym, args, scope, pos) {
        const fb = sym.fb;
        if (fb.builtin) {
            const def = fb_1.BUILTIN_FBS[fb.type];
            const st = fb.builtin;

            let positional = 0;
            const outBinds = [];
            for (const a of args) {
                if (a.isOutput) {
                    if (a.name)
                        outBinds.push({ prop: a.name.toUpperCase(), target: a.value });
                    continue;
                }
                const pname = a.name ? a.name.toUpperCase() : def.inputs[positional++];
                if (!pname) {
                    throw new types_1.PlcError(`Too many arguments for ${fb.type}`, pos.line, pos.col);
                }
                st.in[pname] = this.evalExpr(a.value, scope);
            }
            def.call(st, (k) => st.in[k], this.dt);

            for (const ob of outBinds) {
                if (ob.prop in st.out)
                    this.assign(ob.target, st.out[ob.prop], scope);
            }
            return st.out[def.outputs[0]] ?? false;
        }

        const def = this.fbDefs.get(fb.type);
        const inner = fb.userScope;
        if (!def || !inner) {
            throw new types_1.PlcError(`Definition not found for ${fb.type}`, pos.line, pos.col);
        }
        const inputs = def.vars.filter((v) => v.scope === 'input' || v.scope === 'inout');
        let positional = 0;
        const outBinds = [];
        for (const a of args) {
            if (a.isOutput) {
                if (a.name)
                    outBinds.push({ prop: (0, types_1.normKey)(a.name), target: a.value });
                continue;
            }
            const pkey = a.name ? (0, types_1.normKey)(a.name) : inputs[positional++]?.key;
            if (!pkey)
                throw new types_1.PlcError(`Too many arguments for ${fb.type}`, pos.line, pos.col);
            const target = inner.vars.get(pkey);
            if (!target)
                throw new types_1.PlcError(`${fb.type} has no input ${a.name ?? pkey}`, pos.line, pos.col);
            target.value = (0, types_1.coerce)(this.evalExpr(a.value, scope), target.decl.type);
        }
        this.execBlock(def.body, inner);
        for (const ob of outBinds) {
            const src = inner.vars.get(ob.prop);
            if (src)
                this.assign(ob.target, src.value, scope);
        }
        const firstOut = def.vars.find((v) => v.scope === 'output');
        return firstOut ? (inner.vars.get(firstOut.key)?.value ?? false) : false;
    }
    callUserFunction(fn, args, scope, pos) {
        const local = new Scope(this.globals, fn.name);
        for (const v of fn.vars)
            this.declareIn(local, v);

        const retKey = (0, types_1.normKey)(fn.name);
        if (!local.vars.has(retKey)) {
            local.declare({ name: fn.name, key: retKey, type: fn.returnType ?? 'INT', scope: 'temp' });
        }
        const inputs = fn.vars.filter((v) => v.scope === 'input' || v.scope === 'inout');
        let positional = 0;
        for (const a of args) {
            if (a.isOutput)
                continue;
            const pkey = a.name ? (0, types_1.normKey)(a.name) : inputs[positional++]?.key;
            if (!pkey)
                throw new types_1.PlcError(`Too many arguments for ${fn.name}`, pos.line, pos.col);
            const target = local.vars.get(pkey);
            if (!target)
                throw new types_1.PlcError(`${fn.name} has no input ${a.name ?? pkey}`, pos.line, pos.col);
            target.value = (0, types_1.coerce)(this.evalExpr(a.value, scope), target.decl.type);
        }
        this.execBlock(fn.body, local);
        return local.vars.get(retKey)?.value ?? 0;
    }
}
exports.PlcRuntime = PlcRuntime;
