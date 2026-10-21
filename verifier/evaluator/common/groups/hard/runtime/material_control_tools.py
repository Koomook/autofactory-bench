"""ST composition and mechanical helpers; no autonomous production scheduler."""
import re
from generate_material_coordination import compile_st

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
