"use strict";
/**

 *




 *


 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.KEYWORDS = void 0;
exports.parseDuration = parseDuration;
exports.tokenize = tokenize;
const types_1 = require("../types");
exports.KEYWORDS = new Set([
    'PROGRAM', 'END_PROGRAM',
    'FUNCTION_BLOCK', 'END_FUNCTION_BLOCK',
    'FUNCTION', 'END_FUNCTION',
    'VAR', 'VAR_INPUT', 'VAR_OUTPUT', 'VAR_IN_OUT', 'VAR_GLOBAL', 'VAR_TEMP', 'END_VAR',
    'CONSTANT', 'RETAIN', 'AT',
    'IF', 'THEN', 'ELSIF', 'ELSE', 'END_IF',
    'CASE', 'OF', 'END_CASE',
    'FOR', 'TO', 'BY', 'DO', 'END_FOR',
    'WHILE', 'END_WHILE',
    'REPEAT', 'UNTIL', 'END_REPEAT',
    'EXIT', 'CONTINUE', 'RETURN',
    'TRUE', 'FALSE',
    'AND', 'OR', 'XOR', 'NOT', 'MOD',
    'BOOL', 'INT', 'DINT', 'SINT', 'UINT', 'UDINT', 'WORD', 'BYTE', 'DWORD',
    'REAL', 'LREAL', 'TIME', 'STRING', 'ARRAY',
]);

const OPERATORS = [
    ':=', '=>', '<=', '>=', '<>', '**',
    '+', '-', '*', '/', '<', '>', '=', '(', ')', '[', ']', ',', ';', ':', '.',
];
const isDigit = (c) => c >= '0' && c <= '9';
const isIdentStart = (c) => /[A-Za-z_]/.test(c);
const isIdentPart = (c) => /[A-Za-z0-9_]/.test(c);

function parseDuration(body) {
    const src = body.trim().toLowerCase();
    if (!src)
        return null;

    if (/^\d+(\.\d+)?$/.test(src))
        return Math.round(Number(src));
    const re = /(\d+(?:\.\d+)?)(ms|s|m|h|d)/g;
    let total = 0;
    let matched = 0;
    let m;
    while ((m = re.exec(src))) {
        matched += m[0].length;
        const n = Number(m[1]);
        switch (m[2]) {
            case 'ms':
                total += n;
                break;
            case 's':
                total += n * 1000;
                break;
            case 'm':
                total += n * 60000;
                break;
            case 'h':
                total += n * 3600000;
                break;
            case 'd':
                total += n * 86400000;
                break;
        }
    }

    if (matched !== src.replace(/_/g, '').length)
        return null;
    return Math.round(total);
}
function tokenize(src, comments) {
    const tokens = [];
    let i = 0;
    let line = 1;
    let col = 1;

    const pushComment = (text, cline, ccol) => {
        if (!comments)
            return;
        const prev = tokens[tokens.length - 1];
        comments.push({
            text: text.trim(),
            line: cline,
            col: ccol,
            trailing: !!prev && prev.line === cline,
        });
    };
    const advance = (n = 1) => {
        for (let k = 0; k < n; k++) {
            if (src[i] === '\n') {
                line++;
                col = 1;
            }
            else {
                col++;
            }
            i++;
        }
    };
    while (i < src.length) {
        const c = src[i];

        if (c === ' ' || c === '\t' || c === '\r' || c === '\n') {
            advance();
            continue;
        }

        if (c === '(' && src[i + 1] === '*') {
            const startLine = line, startCol = col;
            const from = i + 2;
            advance(2);
            let depth = 1;
            while (i < src.length && depth > 0) {
                if (src[i] === '(' && src[i + 1] === '*') {
                    depth++;
                    advance(2);
                }
                else if (src[i] === '*' && src[i + 1] === ')') {
                    depth--;
                    advance(2);
                }
                else
                    advance();
            }
            if (depth > 0)
                throw new types_1.PlcError('Unclosed comment (* ... *)', startLine, startCol);
            pushComment(src.slice(from, i - 2), startLine, startCol);
            continue;
        }

        if (c === '/' && src[i + 1] === '/') {
            const startLine = line, startCol = col;
            const from = i + 2;
            while (i < src.length && src[i] !== '\n')
                advance();
            pushComment(src.slice(from, i), startLine, startCol);
            continue;
        }

        if (c === '/' && src[i + 1] === '*') {
            const startLine = line, startCol = col;
            const from = i + 2;
            advance(2);
            while (i < src.length && !(src[i] === '*' && src[i + 1] === '/'))
                advance();
            if (i >= src.length)
                throw new types_1.PlcError('Unclosed block comment', startLine, startCol);
            pushComment(src.slice(from, i), startLine, startCol);
            advance(2);
            continue;
        }
        const startLine = line;
        const startCol = col;

        if (c === '%') {
            let j = i + 1;
            while (j < src.length && /[A-Za-z0-9.]/.test(src[j]))
                j++;
            const text = src.slice(i, j);
            advance(j - i);
            tokens.push({ kind: 'ident', text, value: text.toUpperCase(), line: startLine, col: startCol });
            continue;
        }

        if (c === "'" || c === '"') {
            const quote = c;
            advance();
            let out = '';
            while (i < src.length && src[i] !== quote) {
                if (src[i] === '$' && i + 1 < src.length) {

                    const e = src[i + 1].toUpperCase();
                    const map = { R: '\r', L: '\n', N: '\n', T: '\t', P: '\f', $: '$', "'": "'", '"': '"' };
                    out += map[e] ?? src[i + 1];
                    advance(2);
                    continue;
                }
                out += src[i];
                advance();
            }
            if (i >= src.length)
                throw new types_1.PlcError('Unclosed string', startLine, startCol);
            advance(); // closing quote
            tokens.push({ kind: 'str', text: out, value: out, line: startLine, col: startCol });
            continue;
        }

        if (isDigit(c)) {
            let j = i;
            while (j < src.length && /[0-9_]/.test(src[j]))
                j++;

            if (src[j] === '#') {
                const base = Number(src.slice(i, j).replace(/_/g, ''));
                let k = j + 1;
                while (k < src.length && /[0-9A-Fa-f_]/.test(src[k]))
                    k++;
                const digits = src.slice(j + 1, k).replace(/_/g, '');
                const n = parseInt(digits, base);
                if (!isFinite(n) || Number.isNaN(n)) {
                    throw new types_1.PlcError(`Invalid base-${base} literal: ${src.slice(i, k)}`, startLine, startCol);
                }
                const text = src.slice(i, k);
                advance(k - i);
                tokens.push({ kind: 'num', text, value: text, num: n, line: startLine, col: startCol });
                continue;
            }

            if (src[j] === '.' && isDigit(src[j + 1])) {
                j++;
                while (j < src.length && /[0-9_]/.test(src[j]))
                    j++;
            }

            if (src[j] === 'e' || src[j] === 'E') {
                let k = j + 1;
                if (src[k] === '+' || src[k] === '-')
                    k++;
                if (isDigit(src[k])) {
                    k++;
                    while (k < src.length && isDigit(src[k]))
                        k++;
                    j = k;
                }
            }
            const text = src.slice(i, j);
            advance(j - i);
            tokens.push({ kind: 'num', text, value: text, num: Number(text.replace(/_/g, '')), line: startLine, col: startCol });
            continue;
        }

        if (isIdentStart(c)) {
            let j = i;
            while (j < src.length && isIdentPart(src[j]))
                j++;
            const word = src.slice(i, j);
            const upper = word.toUpperCase();

            if (src[j] === '#' && (upper === 'T' || upper === 'TIME' || upper === 'LTIME')) {
                let k = j + 1;
                while (k < src.length && /[0-9A-Za-z._]/.test(src[k]))
                    k++;
                const body = src.slice(j + 1, k);
                const ms = parseDuration(body);
                if (ms === null) {
                    throw new types_1.PlcError(`Invalid time literal: ${word}#${body}`, startLine, startCol);
                }
                const text = src.slice(i, k);
                advance(k - i);
                tokens.push({ kind: 'time', text, value: text, num: ms, line: startLine, col: startCol });
                continue;
            }

            if (src[j] === '#' && (upper === 'D' || upper === 'DT' || upper === 'TOD' || upper === 'DATE')) {
                throw new types_1.PlcError(`Date/time literal (${upper}#) is not supported`, startLine, startCol);
            }
            advance(j - i);
            if (exports.KEYWORDS.has(upper)) {
                tokens.push({ kind: 'kw', text: word, value: upper, line: startLine, col: startCol });
            }
            else {
                tokens.push({ kind: 'ident', text: word, value: word, line: startLine, col: startCol });
            }
            continue;
        }

        const op = OPERATORS.find((o) => src.startsWith(o, i));
        if (op) {
            advance(op.length);
            tokens.push({ kind: 'op', text: op, value: op, line: startLine, col: startCol });
            continue;
        }
        throw new types_1.PlcError(`Unknown character '${c}'`, startLine, startCol);
    }
    tokens.push({ kind: 'eof', text: '', value: '', line, col });
    return tokens;
}
