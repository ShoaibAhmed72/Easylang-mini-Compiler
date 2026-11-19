"""C++17 visualization helpers for EasyLang Studio.

Clang-backed AST/LLVM IR are preferred. Token, symbol and CFG views have
source-based fallbacks and are explicitly labeled as approximate.
"""
from __future__ import annotations
import json, re, shutil, subprocess
from pathlib import Path
from visualizations.cfg_builder import ControlFlowGraph, CFGNode, CFGEdge

TOKEN_RE = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|::|->|\+\+|--|==|!=|<=|>=|&&|\|\||<<|>>|[+\-*/%=&|^!<>~?:.,;(){}\[\]]', re.S)
DECL_RE = re.compile(r'\b(?:const\s+)?(?:unsigned\s+|signed\s+)?(?:int|long|short|char|float|double|bool|auto|string|std::string|[A-Z]\w*)\s+([A-Za-z_]\w*)\s*(?:[=;,(]|\[)', re.M)


def tokenize_cpp(source: str):
    out=[]
    for m in TOKEN_RE.finditer(source):
        lex=m.group(0)
        if lex.startswith('//') or lex.startswith('/*'):
            typ='COMMENT'
        elif lex.startswith('"') or lex.startswith("'"):
            typ='STRING' if lex.startswith('"') else 'CHAR'
        elif lex[0].isdigit(): typ='NUMBER'
        elif re.match(r'[A-Za-z_]',lex): typ='KEYWORD' if lex in {'int','void','if','else','while','for','return','class','struct','const','auto','bool','char','double','float','long','short','using','namespace','include','switch','case','break','continue'} else 'IDENTIFIER'
        else: typ='OPERATOR' if lex in '+-*/%=<>!&|^~?:' or lex in {'==','!=','<=','>=','&&','||','++','--','<<','>>','::','->'} else 'PUNCTUATION'
        line=source.count('\n',0,m.start())+1
        last=source.rfind('\n',0,m.start())
        col=m.start()-last
        out.append({'type':typ,'lexeme':lex,'line':line,'column':col})
    return out


def _clang_ast_tree(raw, source):
    source_lines=source.splitlines()
    max_nodes=300
    count=[0]
    def loc_line(node):
        loc=node.get('loc') or node.get('range',{}).get('begin',{}).get('loc') or node.get('range',{}).get('begin',{})
        line=loc.get('line')
        if line is None and loc.get('offset') is not None:
            line=source.count('\n',0,int(loc['offset']))+1
        return int(line or 1)
    def convert(node, depth=0):
        if not isinstance(node,dict) or count[0]>=max_nodes or depth>45: return None
        kind=node.get('kind')
        if not kind: return None
        count[0]+=1
        name=node.get('name','')
        value=node.get('value') or node.get('opcode') or node.get('type',{}).get('qualType','')
        if name and value: value=f'{name} — {value}'
        elif name: value=name
        elif value: value=str(value)
        children=[]
        for child in node.get('inner',[]) or []:
            c=convert(child,depth+1)
            if c: children.append(c)
        return {'name':kind,'value':value,'line':loc_line(node),'column':1,'children':children}
    return convert(raw) or {'name':'TranslationUnit','value':'Clang AST','line':1,'column':1,'children':[]}


def _fallback_ast(source):
    """A source-structure tree fallback; explicitly not a compiler AST."""
    root={'name':'C++ Source Structure (approximate)','value':'Clang AST unavailable','line':1,'column':1,'children':[]}
    for line_no,line in enumerate(source.splitlines(),1):
        text=line.strip()
        if not text or text.startswith('#') or text.startswith('//'): continue
        kind='Statement'
        if re.search(r'\b(if|else|for|while|switch)\b',text): kind='Control Statement'
        elif re.search(r'\b(return)\b',text): kind='Return Statement'
        elif re.search(r'\b(class|struct)\b',text): kind='Type Declaration'
        elif re.search(r'\b(?:int|float|double|char|bool|auto|string|void)\s+\w+',text): kind='Declaration/Function'
        root['children'].append({'name':kind,'value':text[:180],'line':line_no,'column':1,'children':[]})
    return root


def _symbols(source):
    symbols=[]
    for match in DECL_RE.finditer(source):
        line=source.count('\n',0,match.start())+1
        before=source[:match.start()].splitlines()[-1] if source[:match.start()].splitlines() else ''
        # Skip obvious function declarations/definitions (name immediately followed by '(')
        if re.match(r'\s*\(', source[match.end()-1:match.end()+2]): continue
        decl=match.group(0).strip()
        type_part=decl[:decl.find(match.group(1))].strip()
        symbols.append({'name':match.group(1),'type':type_part or 'unknown','value':'<not evaluated>','scope':'source scope (approx.)','line':line,'initialized':'=' in decl})
    return symbols


def _source_cfg(source):
    """Approximate source-line flow graph; not a compiler CFG."""
    graph=ControlFlowGraph()
    graph.nodes[0]=CFGNode(0,'entry','Entry')
    graph.nodes[1]=CFGNode(1,'exit','Exit')
    statements=[]
    for line_no,line in enumerate(source.splitlines(),1):
        stripped=line.strip()
        if not stripped or stripped.startswith('#') or stripped.startswith('//') or stripped in ('{','}','};'): continue
        if stripped.startswith('/*'): continue
        kind='decision' if re.search(r'\b(if|while|for|switch)\b',stripped) else 'block'
        statements.append((line_no,stripped,kind))
    if not statements:
        graph.edges.append(CFGEdge(0,1)); return graph
    prev=0
    for idx,(line,text,kind) in enumerate(statements,2):
        graph.nodes[idx]=CFGNode(idx,kind,text[:160],line)
        graph.edges.append(CFGEdge(prev,idx))
        prev=idx
    graph.edges.append(CFGEdge(prev,1))
    # Add clearly labeled approximate branch and loop edges.
    for idx,(line,text,kind) in enumerate(statements,2):
        if re.search(r'\b(if|switch)\b',text):
            next_idx = idx + 1
            if next_idx <= prev:
                graph.edges.append(CFGEdge(idx, next_idx, 'True (approximate)'))
                graph.edges.append(CFGEdge(idx, 1, 'False/merge (approximate)'))
        if re.search(r'\b(while|for)\b',text) and idx+1<=prev:
            graph.edges.append(CFGEdge(prev,idx,'Loop back (approximate)'))
    return graph


def analyze_cpp(source, source_path=None):
    data={'tokens':tokenize_cpp(source),'symbols':_symbols(source),'cfg':_source_cfg(source),
          'ast_tree':None,'ast_detail':'Source-structure fallback (approximate); Clang AST unavailable.',
          'ir':'LLVM IR unavailable; Clang not found or IR extraction failed.', 'clang':None}
    clang=shutil.which('clang') or shutil.which('clang++')
    if clang:
        data['clang']=clang
        tmp=Path(source_path) if source_path else None
        if tmp and tmp.exists():
            try:
                run=subprocess.run([clang,'-std=c++17','-Xclang','-ast-dump=json','-fsyntax-only',str(tmp)],capture_output=True,text=True,timeout=30)
                if run.returncode==0 and run.stdout.strip():
                    data['ast_tree']=_clang_ast_tree(json.loads(run.stdout),source)
                    data['ast_detail']='Clang AST extracted from the C++ translation unit.'
            except Exception as exc:
                data['ast_detail']=f'Clang AST extraction failed; fallback is approximate: {exc}'
            try:
                ir=subprocess.run([clang,'-std=c++17','-S','-emit-llvm','-o','-','-x','c++',str(tmp)],capture_output=True,text=True,timeout=30)
                if ir.returncode==0 and ir.stdout:
                    data['ir']=ir.stdout
            except Exception:
                pass
    if data['ast_tree'] is None: data['ast_tree']=_fallback_ast(source)
    return data
