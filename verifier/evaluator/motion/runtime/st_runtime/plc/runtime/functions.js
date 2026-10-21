"use strict";
/**
 * Stateless IEC 61131-3 standard functions.
 * Arguments arrive as already evaluated values.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.STD_FUNCTIONS = void 0;
exports.isStdFunction = isStdFunction;
const n = (v) => (typeof v === 'boolean' ? (v ? 1 : 0) : Number(v) || 0);
const b = (v) => (typeof v === 'boolean' ? v : Number(v) !== 0);
exports.STD_FUNCTIONS = {
    // Arithmetic.
    ABS: (a) => Math.abs(n(a[0])),
    SQRT: (a) => Math.sqrt(Math.max(0, n(a[0]))),
    LN: (a) => Math.log(Math.max(1e-12, n(a[0]))),
    LOG: (a) => Math.log10(Math.max(1e-12, n(a[0]))),
    EXP: (a) => Math.exp(n(a[0])),
    SIN: (a) => Math.sin(n(a[0])),
    COS: (a) => Math.cos(n(a[0])),
    TAN: (a) => Math.tan(n(a[0])),
    ASIN: (a) => Math.asin(n(a[0])),
    ACOS: (a) => Math.acos(n(a[0])),
    ATAN: (a) => Math.atan(n(a[0])),
    ATAN2: (a) => Math.atan2(n(a[0]), n(a[1])),
    // Selection and comparison.
    MIN: (a) => Math.min(...a.map(n)),
    MAX: (a) => Math.max(...a.map(n)),
    LIMIT: (a) => Math.min(n(a[2]), Math.max(n(a[0]), n(a[1]))), // LIMIT(MN, IN, MX)
    SEL: (a) => (b(a[0]) ? a[2] : a[1]), // SEL(G, IN0, IN1)
    MUX: (a) => a[Math.trunc(n(a[0])) + 1] ?? a[1],
    // Type conversion.
    TRUNC: (a) => Math.trunc(n(a[0])),
    ROUND: (a) => Math.round(n(a[0])),
    FLOOR: (a) => Math.floor(n(a[0])),
    CEIL: (a) => Math.ceil(n(a[0])),
    REAL: (a) => n(a[0]),
    LREAL: (a) => n(a[0]),
    INT: (a) => Math.trunc(n(a[0])),
    DINT: (a) => Math.trunc(n(a[0])),
    SINT: (a) => Math.trunc(n(a[0])),
    WORD: (a) => Math.trunc(n(a[0])) & 0xffff,
    BYTE: (a) => Math.trunc(n(a[0])) & 0xff,
    DWORD: (a) => Math.trunc(n(a[0])) >>> 0,
    BOOL: (a) => b(a[0]),
    TIME: (a) => Math.trunc(n(a[0])),
    BOOL_TO_INT: (a) => (b(a[0]) ? 1 : 0),
    INT_TO_BOOL: (a) => b(a[0]),
    INT_TO_REAL: (a) => n(a[0]),
    REAL_TO_INT: (a) => Math.round(n(a[0])),
    TIME_TO_INT: (a) => Math.trunc(n(a[0])),
    INT_TO_TIME: (a) => Math.trunc(n(a[0])),
    // Bit operations.
    SHL: (a) => (Math.trunc(n(a[0])) << Math.trunc(n(a[1]))) & 0xffff,
    SHR: (a) => (Math.trunc(n(a[0])) & 0xffff) >>> Math.trunc(n(a[1])),
    ROL: (a) => {
        const v = Math.trunc(n(a[0])) & 0xffff;
        const s = Math.trunc(n(a[1])) % 16;
        return ((v << s) | (v >>> (16 - s))) & 0xffff;
    },
    ROR: (a) => {
        const v = Math.trunc(n(a[0])) & 0xffff;
        const s = Math.trunc(n(a[1])) % 16;
        return ((v >>> s) | (v << (16 - s))) & 0xffff;
    },
    AND_WORD: (a) => a.map(n).reduce((x, y) => x & y),
    OR_WORD: (a) => a.map(n).reduce((x, y) => x | y),
    XOR_WORD: (a) => a.map(n).reduce((x, y) => x ^ y),
    NOT_WORD: (a) => ~Math.trunc(n(a[0])) & 0xffff,
    // Moves.
    MOVE: (a) => a[0],
    // Limited string operations.
    LEN: (a) => String(a[0]).length,
    CONCAT: (a) => a.map(String).join(''),
};
function isStdFunction(name) {
    return name.toUpperCase() in exports.STD_FUNCTIONS;
}
