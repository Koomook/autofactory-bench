"use strict";
/**
 * IEC 61131-3 standard function blocks.
 *
 * Each block computes outputs from its state, inputs, and elapsed time.
 * Time uses integer milliseconds; dt is the duration of the current scan.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.BUILTIN_FBS = void 0;
exports.fbOutputNames = fbOutputNames;
const bool = (v, dflt = false) => v === undefined ? dflt : typeof v === 'boolean' ? v : Number(v) !== 0;
const num = (v, dflt = 0) => v === undefined ? dflt : typeof v === 'boolean' ? (v ? 1 : 0) : Number(v) || 0;
/** On-delay timer: Q rises only after IN stays true for PT. */
const TON = {
    inputs: ['IN', 'PT'],
    outputs: ['Q', 'ET'],
    init: () => ({ out: { Q: false, ET: 0 }, mem: { running: false }, in: {} }),
    call(s, get, dt) {
        const IN = bool(get('IN'));
        const PT = num(get('PT'));
        if (!IN) {
            s.mem.running = false;
            s.out.ET = 0;
            s.out.Q = false;
            return;
        }
        // The first TRUE call establishes t=0, rather than charging the
        // preceding scan interval to an input that has only just become TRUE.
        // Scope: one call per scan, fixed PT during an active interval.
        const et = Math.min(PT, s.mem.running ? num(s.out.ET) + dt : 0);
        s.mem.running = true;
        s.out.ET = et;
        s.out.Q = et >= PT;
    },
};
/** Off-delay timer: Q remains true for PT after IN falls. */
const TOF = {
    inputs: ['IN', 'PT'],
    outputs: ['Q', 'ET'],
    init: () => ({ out: { Q: false, ET: 0 }, mem: {}, in: {} }),
    call(s, get, dt) {
        const IN = bool(get('IN'));
        const PT = num(get('PT'));
        if (IN) {
            s.out.ET = 0;
            s.out.Q = true;
            return;
        }
        if (!s.out.Q) {
            s.out.ET = PT;
            return;
        }
        const et = Math.min(PT, num(s.out.ET) + dt);
        s.out.ET = et;
        s.out.Q = et < PT;
    },
};
/** Pulse timer: emit one PT-long pulse on an IN rising edge. */
const TP = {
    inputs: ['IN', 'PT'],
    outputs: ['Q', 'ET'],
    init: () => ({ out: { Q: false, ET: 0 }, mem: { prev: false, running: false }, in: {} }),
    call(s, get, dt) {
        const IN = bool(get('IN'));
        const PT = num(get('PT'));
        const prev = !!s.mem.prev;
        if (!s.mem.running && IN && !prev) {
            s.mem.running = true;
            s.out.ET = 0;
            s.out.Q = true;
        }
        else if (s.mem.running) {
            const et = Math.min(PT, num(s.out.ET) + dt);
            s.out.ET = et;
            if (et >= PT) {
                s.out.Q = false;
                // IN must fall before another pulse can be triggered.
                if (!IN) {
                    s.mem.running = false;
                    s.out.ET = 0;
                }
            }
        }
        s.mem.prev = IN;
    },
};
/** Up counter. */
const CTU = {
    inputs: ['CU', 'R', 'PV'],
    outputs: ['Q', 'CV'],
    init: () => ({ out: { Q: false, CV: 0 }, mem: { prev: false }, in: {} }),
    call(s, get) {
        const CU = bool(get('CU'));
        const R = bool(get('R'));
        const PV = num(get('PV'));
        if (R) {
            s.out.CV = 0;
        }
        else if (CU && !s.mem.prev) {
            s.out.CV = Math.min(32767, num(s.out.CV) + 1);
        }
        s.out.Q = num(s.out.CV) >= PV;
        s.mem.prev = CU;
    },
};
/** Down counter. */
const CTD = {
    inputs: ['CD', 'LD', 'PV'],
    outputs: ['Q', 'CV'],
    init: () => ({ out: { Q: false, CV: 0 }, mem: { prev: false }, in: {} }),
    call(s, get) {
        const CD = bool(get('CD'));
        const LD = bool(get('LD'));
        const PV = num(get('PV'));
        if (LD) {
            s.out.CV = PV;
        }
        else if (CD && !s.mem.prev) {
            s.out.CV = Math.max(-32768, num(s.out.CV) - 1);
        }
        s.out.Q = num(s.out.CV) <= 0;
        s.mem.prev = CD;
    },
};
/** Up/down counter. */
const CTUD = {
    inputs: ['CU', 'CD', 'R', 'LD', 'PV'],
    outputs: ['QU', 'QD', 'CV'],
    init: () => ({ out: { QU: false, QD: false, CV: 0 }, mem: { prevU: false, prevD: false }, in: {} }),
    call(s, get) {
        const CU = bool(get('CU'));
        const CD = bool(get('CD'));
        const R = bool(get('R'));
        const LD = bool(get('LD'));
        const PV = num(get('PV'));
        if (R)
            s.out.CV = 0;
        else if (LD)
            s.out.CV = PV;
        else {
            let cv = num(s.out.CV);
            if (CU && !s.mem.prevU)
                cv++;
            if (CD && !s.mem.prevD)
                cv--;
            s.out.CV = Math.max(-32768, Math.min(32767, cv));
        }
        s.out.QU = num(s.out.CV) >= PV;
        s.out.QD = num(s.out.CV) <= 0;
        s.mem.prevU = CU;
        s.mem.prevD = CD;
    },
};
/** Rising-edge detector. */
const R_TRIG = {
    inputs: ['CLK'],
    outputs: ['Q'],
    init: () => ({ out: { Q: false }, mem: { prev: false }, in: {} }),
    call(s, get) {
        const CLK = bool(get('CLK'));
        s.out.Q = CLK && !s.mem.prev;
        s.mem.prev = CLK;
    },
};
/** Falling-edge detector. */
const F_TRIG = {
    inputs: ['CLK'],
    outputs: ['Q'],
    init: () => ({ out: { Q: false }, mem: { prev: true }, in: {} }),
    call(s, get) {
        const CLK = bool(get('CLK'));
        s.out.Q = !CLK && !!s.mem.prev;
        s.mem.prev = CLK;
    },
};
/** Reset-priority flip-flop. */
const RS = {
    inputs: ['SET', 'RESET1'],
    outputs: ['Q1'],
    init: () => ({ out: { Q1: false }, mem: {}, in: {} }),
    call(s, get) {
        if (bool(get('RESET1')))
            s.out.Q1 = false;
        else if (bool(get('SET')))
            s.out.Q1 = true;
    },
};
/** Set-priority flip-flop. */
const SR = {
    inputs: ['SET1', 'RESET'],
    outputs: ['Q1'],
    init: () => ({ out: { Q1: false }, mem: {}, in: {} }),
    call(s, get) {
        if (bool(get('SET1')))
            s.out.Q1 = true;
        else if (bool(get('RESET')))
            s.out.Q1 = false;
    },
};
exports.BUILTIN_FBS = {
    TON, TOF, TP, CTU, CTD, CTUD, R_TRIG, F_TRIG, RS, SR,
};
/** Return an FB member's initial value when read before its first call (for example T1.Q). */
function fbOutputNames(type) {
    return exports.BUILTIN_FBS[type]?.outputs ?? [];
}
