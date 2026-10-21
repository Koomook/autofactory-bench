"""ST composition helpers, independent of task-authoring tools."""
import re

def compile_st(b,body):
    aliases={**{'I_'+k:v for sec in ('inputs','word_inputs') for k,v in b[sec].items()},
             **{'O_'+k:v for sec in ('outputs','word_outputs') for k,v in b[sec].items()},'START':'X0'}
    decl='PROGRAM COORDINATION\nVAR_INPUT\n'
    decl+='\n'.join(f'{v} : {"INT" if v.startswith("D") else "BOOL"}; (* {k} *)' for k,v in aliases.items() if k.startswith('I_') or k=='START')
    decl+='\nEND_VAR\nVAR_OUTPUT\n'+'\n'.join(f'{v} : {"INT" if v.startswith("D") else "BOOL"}; (* {k} *)' for k,v in aliases.items() if k.startswith('O_'))
    decl+='\nEND_VAR\nVAR\n state : INT; src : INT; dst : INT; selected : INT; wanted : INT; active : BOOL;\nEND_VAR\n'
    code='IF START THEN active := TRUE; END_IF;\n'+'\n'.join('O_'+k+' := FALSE;' for k in b['outputs'])+'\nIF active THEN\n'+body+'\nEND_IF;\nEND_PROGRAM\n'
    return decl+re.sub(r'\b[IO]_[a-z0-9_]+\b|\bSTART\b',lambda m:aliases[m[0]],code)

def body_of(program,b,variant):
 text=program(b,variant)
 inverse={v:'I_'+k for sec in ['inputs','word_inputs'] for k,v in b[sec].items()}
 inverse.update({v:'O_'+k for sec in ['outputs','word_outputs'] for k,v in b[sec].items()})
 body=text.split('IF active THEN\n',1)[1].rsplit('\nEND_IF;\nEND_PROGRAM',1)[0]
 body=re.sub(r'\b[XYD][0-9A-F]+\b',lambda m:inverse.get(m[0],m[0]),body)
 locals=text.split('\nVAR\n',1)[1].split('\nEND_VAR',1)[0]
 return body,locals

def compile_body(b,body,locals='',extra=''):
 s=compile_st(b,body)
 original=s.split('\nVAR\n',1)[1].split('\nEND_VAR',1)[0]
 return s.replace('\nVAR\n'+original+'\nEND_VAR','\nVAR\n'+(locals or original)+'\n'+extra+'\nEND_VAR',1)
