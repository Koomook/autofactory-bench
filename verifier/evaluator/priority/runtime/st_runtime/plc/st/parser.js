"use strict";
/**

 *


 *


 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.BUILTIN_FB = void 0;
exports.parseST = parseST;
exports.parseExpression = parseExpression;
const types_1 = require("../types");
const lexer_1 = require("./lexer");

const TYPE_MAP = {
    BOOL: 'BOOL',
    SINT: 'INT', INT: 'INT', UINT: 'INT',
    DINT: 'DINT', UDINT: 'DINT', LINT: 'DINT', ULINT: 'DINT',
    BYTE: 'WORD', WORD: 'WORD', DWORD: 'WORD', LWORD: 'WORD',
    REAL: 'REAL', LREAL: 'REAL',
    TIME: 'TIME', LTIME: 'TIME',
    STRING: 'STRING', WSTRING: 'STRING',
};

exports.BUILTIN_FB = new Set([
    'TON', 'TOF', 'TP', 'CTU', 'CTD', 'CTUD', 'R_TRIG', 'F_TRIG', 'RS', 'SR',
]);
const VAR_BLOCK_SCOPE = {
    VAR: 'memory',
    VAR_INPUT: 'input',
    VAR_OUTPUT: 'output',
    VAR_IN_OUT: 'inout',
    VAR_GLOBAL: 'global',
    VAR_TEMP: 'temp',
};
class Parser {
    constructor(tokens, comments) {
        this.tokens = tokens;
        this.p = 0;

        this.trailing = new Map();

        this.leading = new Map();
        for (const c of comments) {
            if (!c.text)
                continue;
            const map = c.trailing ? this.trailing : this.leading;

            if (!map.has(c.line))
                map.set(c.line, c.text);
        }
    }

    get cur() {
        return this.tokens[this.p];
    }
    peek(n = 1) {
        return this.tokens[Math.min(this.p + n, this.tokens.length - 1)];
    }
    next() {
        return this.tokens[this.p++];
    }
    at(value) {
        const t = this.cur;
        return (t.kind === 'kw' || t.kind === 'op') && t.value === value;
    }
    atAny(...values) {
        return values.some((v) => this.at(v));
    }
    accept(value) {
        if (this.at(value)) {
            this.p++;
            return true;
        }
        return false;
    }
    expect(value, what) {
        if (!this.at(value)) {
            const t = this.cur;
            const got = t.kind === 'eof' ? 'end of file' : `'${t.text}'`;
            throw new types_1.PlcError(`Expected ${what ?? `'${value}'`}, found ${got}`, t.line, t.col, Math.max(1, t.text.length));
        }
        return this.next();
    }
    pos(t = this.cur) {
        return { line: t.line, col: t.col };
    }
    fail(msg, t = this.cur) {
        throw new types_1.PlcError(msg, t.line, t.col, Math.max(1, t.text.length));
    }

    parse() {
        const pous = [];
        const globals = [];
        const implicitVars = [];
        const implicitBody = [];
        const implicitLine = this.cur.line;
        while (this.cur.kind !== 'eof') {
            if (this.atAny('PROGRAM', 'FUNCTION_BLOCK', 'FUNCTION')) {
                pous.push(this.parsePou());
            }
            else if (this.at('VAR_GLOBAL')) {
                globals.push(...this.parseVarBlock());
            }
            else if (this.cur.kind === 'kw' && VAR_BLOCK_SCOPE[this.cur.value]) {
                implicitVars.push(...this.parseVarBlock());
            }
            else if (this.accept(';')) {

            }
            else {
                implicitBody.push(this.parseStatement());
            }
        }
        if (implicitVars.length || implicitBody.length) {
            pous.push({
                kind: 'PROGRAM',
                name: 'MAIN',
                vars: implicitVars,
                body: implicitBody,
                line: implicitLine,
            });
        }
        return { pous, globals };
    }
    parsePou() {
        const head = this.next(); // PROGRAM | FUNCTION_BLOCK | FUNCTION
        const kind = head.value;
        const nameTok = this.cur;
        if (nameTok.kind !== 'ident')
            this.fail('POU name required', nameTok);
        const name = this.next().text;
        let returnType;
        if (kind === 'FUNCTION' && this.accept(':')) {
            returnType = this.parseTypeName().type;
        }
        const vars = [];
        while (this.cur.kind === 'kw' && VAR_BLOCK_SCOPE[this.cur.value]) {
            vars.push(...this.parseVarBlock());
        }
        const endKw = `END_${kind}`;
        const body = [];
        while (!this.at(endKw)) {
            if (this.cur.kind === 'eof')
                this.fail(`Missing ${endKw}`, this.cur);
            if (this.accept(';'))
                continue;
            body.push(this.parseStatement());
        }
        this.expect(endKw);
        this.accept(';');
        return { kind, name, vars, body, returnType, line: head.line };
    }

    parseVarBlock() {
        const head = this.next();
        const scope = VAR_BLOCK_SCOPE[head.value];

        while (this.atAny('CONSTANT', 'RETAIN'))
            this.next();
        const out = [];
        while (!this.at('END_VAR')) {
            if (this.cur.kind === 'eof')
                this.fail('Missing END_VAR', this.cur);
            if (this.accept(';'))
                continue;
            out.push(...this.parseVarLine(scope));
        }
        this.expect('END_VAR');
        this.accept(';');
        return out;
    }

    parseVarLine(scope) {
        const declLine = this.cur.line;
        const names = [];
        for (;;) {
            const t = this.cur;
            if (t.kind !== 'ident')
                this.fail('Variable name required', t);
            names.push({ name: this.next().text, line: t.line });
            if (!this.accept(','))
                break;
        }
        let address;
        if (this.accept('AT')) {
            const t = this.cur;
            if (t.kind !== 'ident' || !t.text.startsWith('%'))
                this.fail('AT must be followed by an address such as %IX0.0', t);
            const parsed = (0, types_1.parseAddress)(this.next().text);
            if (!parsed)
                this.fail(`Invalid address format: ${t.text}`, t);
            address = parsed;
        }
        this.expect(':', "':' in variable declaration");
        const ty = this.parseTypeName();
        let initial;
        if (this.accept(':=')) {
            const at = this.cur;
            const e = this.parseExpr();

            if (e.k === 'un' && (e.op === '-' || e.op === '+') && e.e.k === 'lit' && typeof e.e.value === 'number') {
                initial = e.op === '-' ? -e.e.value : e.e.value;
            }
            else if (e.k === 'lit') {
                initial = e.value;
            }
            else {
                this.fail('Initializer must be a literal', at);
            }
        }
        const endLine = this.cur.line;
        this.expect(';', "';' at end of variable declaration");

        const comment = this.trailing.get(endLine) ??
            this.trailing.get(declLine) ??
            this.leading.get(declLine - 1);
        return names.map(({ name, line }) => ({
            name,
            key: (0, types_1.normKey)(name),
            type: ty.type,
            scope,
            address,
            initial,
            comment,
            fbType: ty.fbType,
            dim: ty.dim,
            line,
        }));
    }
    parseTypeName() {
        // ARRAY[0..9] OF INT
        if (this.accept('ARRAY')) {
            this.expect('[');
            const lo = this.parseIntLiteral();
            this.expect('.');
            this.expect('.');
            const hi = this.parseIntLiteral();
            this.expect(']');
            this.expect('OF');
            const inner = this.parseTypeName();
            return { type: inner.type, fbType: inner.fbType, dim: [lo, hi] };
        }
        const t = this.next();
        const upper = t.value.toUpperCase();
        const mapped = TYPE_MAP[upper];
        if (mapped) {

            if (this.at('[')) {
                this.next();
                this.parseIntLiteral();
                this.expect(']');
            }
            return { type: mapped };
        }
        if (t.kind === 'ident') {

            return { type: 'BOOL', fbType: upper };
        }
        this.fail(`Unknown type: ${t.text}`, t);
    }
    parseIntLiteral() {


        const t = this.cur;
        let sign = 1;
        if (this.accept('-'))
            sign = -1;
        else
            this.accept('+');
        const n = this.next();
        if (n.kind !== 'num' || n.num === undefined)
            this.fail('Integer required', t);
        return sign * Math.trunc(n.num);
    }

    parseStatement() {
        const t = this.cur;
        switch (t.value) {
            case 'IF': return this.parseIf();
            case 'CASE': return this.parseCase();
            case 'FOR': return this.parseFor();
            case 'WHILE': return this.parseWhile();
            case 'REPEAT': return this.parseRepeat();
            case 'EXIT':
                this.next();
                this.accept(';');
                return { k: 'exit', pos: this.pos(t) };
            case 'CONTINUE':
                this.next();
                this.accept(';');
                return { k: 'continue', pos: this.pos(t) };
            case 'RETURN':
                this.next();
                this.accept(';');
                return { k: 'return', pos: this.pos(t) };
        }

        const target = this.parsePostfix();
        if (this.accept(':=')) {
            const value = this.parseExpr();
            this.expect(';', "';' at end of assignment");
            return { k: 'assign', target, value, pos: this.pos(t) };
        }
        if (target.k === 'call') {
            this.expect(';', "';' at end of call");
            return { k: 'call', name: target.name, args: target.args, pos: this.pos(t) };
        }
        this.fail('Assignment (:=) or call required', this.cur);
    }
    parseThenBody(...stops) {
        const body = [];
        while (!this.atAny(...stops)) {
            if (this.cur.kind === 'eof')
                this.fail(`Expected one of ${stops.join('/')}`, this.cur);
            if (this.accept(';'))
                continue;
            body.push(this.parseStatement());
        }
        return body;
    }
    parseIf() {
        const start = this.expect('IF');
        const branches = [];
        let cond = this.parseExpr();
        this.expect('THEN');
        let body = this.parseThenBody('ELSIF', 'ELSE', 'END_IF');
        branches.push({ cond, body });
        while (this.accept('ELSIF')) {
            cond = this.parseExpr();
            this.expect('THEN');
            body = this.parseThenBody('ELSIF', 'ELSE', 'END_IF');
            branches.push({ cond, body });
        }
        let orElse;
        if (this.accept('ELSE'))
            orElse = this.parseThenBody('END_IF');
        this.expect('END_IF');
        this.accept(';');
        return { k: 'if', branches, orElse, pos: this.pos(start) };
    }
    parseCase() {
        const start = this.expect('CASE');
        const selector = this.parseExpr();
        this.expect('OF');
        const cases = [];
        let orElse;
        while (!this.at('END_CASE')) {
            if (this.cur.kind === 'eof')
                this.fail('Missing END_CASE', this.cur);
            if (this.accept('ELSE')) {
                orElse = this.parseThenBody('END_CASE');
                break;
            }

            const labels = [];
            for (;;) {
                const lo = this.parseCaseLabelValue();
                let hi = lo;
                if (this.at('.') && this.peek().value === '.') {
                    this.next();
                    this.next();
                    hi = this.parseCaseLabelValue();
                }
                labels.push({ lo, hi });
                if (!this.accept(','))
                    break;
            }
            this.expect(':', "':' after CASE label");

            const body = [];
            while (!this.atAny('END_CASE', 'ELSE') && !this.atCaseLabel()) {
                const here = this.cur;
                if (here.kind === 'eof')
                    this.fail('Missing END_CASE', here);
                if (this.accept(';'))
                    continue;
                body.push(this.parseStatement());
            }
            cases.push({ labels, body });
        }
        this.expect('END_CASE');
        this.accept(';');
        return { k: 'case', selector, cases, orElse, pos: this.pos(start) };
    }

    atCaseLabel() {
        let t = this.cur;
        let ahead = 1;
        if ((t.value === '-' || t.value === '+') && t.kind === 'op') {
            t = this.peek();
            ahead = 2;
        }
        if (t.kind !== 'num')
            return false;
        const nxt = this.peek(ahead).value;
        return nxt === ':' || nxt === ',' || nxt === '.';
    }

    parseCaseLabelValue() {
        const t = this.cur;
        if (t.kind === 'num' && t.num !== undefined) {
            this.next();
            return Math.trunc(t.num);
        }
        if (this.at('-') || this.at('+'))
            return this.parseIntLiteral();
        this.fail('CASE label must be an integer', t);
    }
    parseFor() {
        const start = this.expect('FOR');
        const nameTok = this.cur;
        if (nameTok.kind !== 'ident')
            this.fail('FOR control variable required', nameTok);
        const varName = this.next().text;
        this.expect(':=');
        const from = this.parseExpr();
        this.expect('TO');
        const to = this.parseExpr();
        const by = this.accept('BY') ? this.parseExpr() : undefined;
        this.expect('DO');
        const body = this.parseThenBody('END_FOR');
        this.expect('END_FOR');
        this.accept(';');
        return { k: 'for', varName, from, to, by, body, pos: this.pos(start) };
    }
    parseWhile() {
        const start = this.expect('WHILE');
        const cond = this.parseExpr();
        this.expect('DO');
        const body = this.parseThenBody('END_WHILE');
        this.expect('END_WHILE');
        this.accept(';');
        return { k: 'while', cond, body, pos: this.pos(start) };
    }
    parseRepeat() {
        const start = this.expect('REPEAT');
        const body = this.parseThenBody('UNTIL');
        this.expect('UNTIL');
        const until = this.parseExpr();
        this.expect('END_REPEAT');
        this.accept(';');
        return { k: 'repeat', body, until, pos: this.pos(start) };
    }

    parseExpr() {
        return this.parseBin(0);
    }
    parseBin(level) {
        if (level >= Parser.LEVELS.length)
            return this.parsePower();
        let left = this.parseBin(level + 1);
        for (;;) {
            const op = Parser.LEVELS[level].find((o) => this.at(o));
            if (!op)
                return left;
            const t = this.next();
            const right = this.parseBin(level + 1);
            left = { k: 'bin', op, l: left, r: right, pos: this.pos(t) };
        }
    }

    parsePower() {
        const base = this.parseUnary();
        if (this.at('**')) {
            const t = this.next();
            const exp = this.parsePower();
            return { k: 'bin', op: '**', l: base, r: exp, pos: this.pos(t) };
        }
        return base;
    }
    parseUnary() {
        const t = this.cur;
        if (this.accept('NOT'))
            return { k: 'un', op: 'NOT', e: this.parseUnary(), pos: this.pos(t) };
        if (this.accept('-'))
            return { k: 'un', op: '-', e: this.parseUnary(), pos: this.pos(t) };
        if (this.accept('+'))
            return { k: 'un', op: '+', e: this.parseUnary(), pos: this.pos(t) };
        return this.parsePostfix();
    }
    parsePostfix() {
        let e = this.parsePrimary();
        for (;;) {
            const t = this.cur;

            if (this.at('.') && this.peek().kind === 'ident') {
                this.next();
                const prop = this.next().text;
                e = { k: 'member', obj: e, prop, pos: this.pos(t) };
                continue;
            }
            if (this.at('[')) {
                this.next();
                const idx = this.parseExpr();
                this.expect(']');
                e = { k: 'index', obj: e, idx, pos: this.pos(t) };
                continue;
            }
            return e;
        }
    }
    parsePrimary() {
        const t = this.cur;
        if (this.accept('(')) {
            const e = this.parseExpr();
            this.expect(')');
            return e;
        }
        if (this.accept('TRUE'))
            return { k: 'lit', value: true, type: 'BOOL', pos: this.pos(t) };
        if (this.accept('FALSE'))
            return { k: 'lit', value: false, type: 'BOOL', pos: this.pos(t) };
        if (t.kind === 'num') {
            this.next();
            const isReal = /[.eE]/.test(t.text) && !t.text.includes('#');
            return { k: 'lit', value: t.num, type: isReal ? 'REAL' : 'INT', pos: this.pos(t) };
        }
        if (t.kind === 'time') {
            this.next();
            return { k: 'lit', value: t.num, type: 'TIME', pos: this.pos(t) };
        }
        if (t.kind === 'str') {
            this.next();
            return { k: 'lit', value: t.value, type: 'STRING', pos: this.pos(t) };
        }
        if (t.kind === 'ident') {
            this.next();
            if (this.at('(')) {
                const args = this.parseArgs();
                return { k: 'call', name: t.text, args, pos: this.pos(t) };
            }
            return { k: 'var', name: t.text, pos: this.pos(t) };
        }

        if (t.kind === 'kw' && TYPE_MAP[t.value] && this.peek().value === '(') {
            this.next();
            const args = this.parseArgs();
            return { k: 'call', name: t.value, args, pos: this.pos(t) };
        }
        this.fail(`Expected a value, found '${t.kind === 'eof' ? 'end of file' : t.text}'`, t);
    }
    parseArgs() {
        this.expect('(');
        const args = [];
        if (this.accept(')'))
            return args;
        for (;;) {

            if (this.cur.kind === 'ident' && (this.peek().value === ':=' || this.peek().value === '=>')) {
                const name = this.next().text;
                const isOutput = this.next().value === '=>';
                args.push({ name, isOutput, value: this.parseExpr() });
            }
            else {
                args.push({ value: this.parseExpr() });
            }
            if (this.accept(','))
                continue;
            this.expect(')', "')' at end of argument list");
            return args;
        }
    }
}

Parser.LEVELS = [
    ['OR'],
    ['XOR'],
    ['AND'],
    ['=', '<>'],
    ['<', '>', '<=', '>='],
    ['+', '-'],
    ['*', '/', 'MOD'],
];

function parseST(src) {
    const comments = [];
    const tokens = (0, lexer_1.tokenize)(src, comments);
    return new Parser(tokens, comments).parse();
}

function parseExpression(src) {
    const tokens = (0, lexer_1.tokenize)(src);
    const p = new Parser(tokens, []);
    return p.parseExpr();
}
