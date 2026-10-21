"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
/** Expose the ST runtime as a headless JSON-lines process. */
const readline = __importStar(require("node:readline"));
const parser_1 = require("./plc/st/parser");
const vm_1 = require("./plc/runtime/vm");
let runtime = null;
let scanMs = 10;
let watch = [];
function send(value) {
    process.stdout.write(`${JSON.stringify(value)}\n`);
}
const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
lines.on('line', (line) => {
    try {
        const request = JSON.parse(line);
        if (request.op === 'init') {
            runtime = new vm_1.PlcRuntime((0, parser_1.parseST)(request.source ?? ''));
            scanMs = Number(request.scan_ms ?? 10);
            watch = (request.watch ?? []).map((name) => name.toUpperCase());
            const missing = watch.filter((name) => runtime?.get(name) === undefined);
            send({ ok: true, missing });
            return;
        }
        if (request.op === 'scan') {
            if (!runtime)
                throw new Error('ST runtime has not been initialized');
            for (const [name, value] of Object.entries(request.inputs ?? {})) {
                runtime.set(name, value);
            }
            runtime.scan(scanMs);
            if (runtime.fault)
                throw runtime.fault;
            const values = {};
            for (const name of watch) {
                const value = runtime.get(name);
                if (value !== undefined)
                    values[name] = typeof value === 'boolean' ? Number(value) : Number(value);
            }
            send({ ok: true, values });
            return;
        }
        if (request.op === 'close') {
            send({ ok: true });
            process.exit(0);
        }
        throw new Error(`Unsupported operation: ${request.op}`);
    }
    catch (error) {
        const value = error;
        send({ ok: false, error: value.message ?? String(error), line: value.line ?? 0, col: value.col ?? 0 });
    }
});
