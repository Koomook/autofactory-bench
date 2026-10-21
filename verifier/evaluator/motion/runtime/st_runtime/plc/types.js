"use strict";
/**
 * IEC 61131-3 value, type, and symbol model.
 *
 * This simulator covers the types needed by typical equipment sequences:
 * BOOL, integer, real, and TIME. TIME is stored internally as integer
 * milliseconds (T#2s becomes 2000).
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.PlcError = exports.normKey = void 0;
exports.defaultValue = defaultValue;
exports.parseAddress = parseAddress;
exports.typeFromAddress = typeFromAddress;
exports.isNumericType = isNumericType;
exports.coerce = coerce;
exports.formatTime = formatTime;
exports.formatValue = formatValue;
const normKey = (name) => name.toUpperCase();
exports.normKey = normKey;
function defaultValue(type) {
    switch (type) {
        case 'BOOL':
            return false;
        case 'STRING':
            return '';
        default:
            return 0;
    }
}
class PlcError extends Error {
    constructor(message, line = 0, col = 0, length = 1) {
        super(message);
        this.line = line;
        this.col = col;
        this.length = length;
        this.name = 'PlcError';
    }
    toDiagnostic() {
        return {
            severity: 'error',
            message: this.message,
            line: this.line,
            col: this.col,
            length: this.length,
        };
    }
}
exports.PlcError = PlcError;
/** Parse %IX0.0, %QW4, or %MD100; return null for other formats. */
function parseAddress(raw) {
    const m = /^%([IQM])([XBWD]?)(\d+)(?:\.(\d+))?$/i.exec(raw.trim());
    if (!m)
        return null;
    const area = m[1].toUpperCase();
    const size = (m[2] || 'X').toUpperCase();
    return {
        raw: raw.trim().toUpperCase(),
        area,
        size,
        byte: Number(m[3]),
        bit: m[4] ? Number(m[4]) : 0,
    };
}
/** Infer an IEC type from an address: %IX maps to BOOL, %MW to INT, etc. */
function typeFromAddress(a) {
    switch (a.size) {
        case 'X':
            return 'BOOL';
        case 'B':
            return 'INT';
        case 'W':
            return 'INT';
        case 'D':
            return 'DINT';
    }
}
function isNumericType(t) {
    return t === 'INT' || t === 'DINT' || t === 'WORD' || t === 'REAL' || t === 'TIME';
}
/** Coerce values on assignment, following common permissive PLC conversions. */
function coerce(value, type) {
    switch (type) {
        case 'BOOL':
            return typeof value === 'boolean' ? value : Number(value) !== 0;
        case 'REAL':
            return typeof value === 'boolean' ? (value ? 1 : 0) : Number(value);
        case 'STRING':
            return String(value);
        case 'INT':
        case 'DINT':
        case 'WORD':
        case 'TIME': {
            const n = typeof value === 'boolean' ? (value ? 1 : 0) : Number(value);
            return Math.trunc(n);
        }
    }
}
/** Format a TIME value in milliseconds as T#1h2m3s450ms for HMI display. */
function formatTime(ms) {
    if (!isFinite(ms))
        return 'T#0ms';
    let rest = Math.max(0, Math.trunc(ms));
    const h = Math.floor(rest / 3600000);
    rest -= h * 3600000;
    const m = Math.floor(rest / 60000);
    rest -= m * 60000;
    const s = Math.floor(rest / 1000);
    const msec = rest - s * 1000;
    let out = '';
    if (h)
        out += `${h}h`;
    if (m)
        out += `${m}m`;
    if (s)
        out += `${s}s`;
    if (msec || !out)
        out += `${msec}ms`;
    return `T#${out}`;
}
/** Convert a value to an HMI display string. */
function formatValue(v, type) {
    if (type === 'TIME')
        return formatTime(Number(v));
    if (typeof v === 'boolean')
        return v ? 'TRUE' : 'FALSE';
    if (typeof v === 'number')
        return Number.isInteger(v) ? String(v) : v.toFixed(3);
    return String(v);
}
