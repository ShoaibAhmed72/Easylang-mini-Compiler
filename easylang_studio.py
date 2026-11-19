
from __future__ import annotations
import os, re, sys, json, shutil, subprocess, threading, time, tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from dataclasses import dataclass, field
from pathlib import Path
from collections import OrderedDict, deque

# ============================== Compiler core ==============================
class CompilerError(Exception):
    HINTS={
        "Lexical":"Check quotes, escapes, and supported characters.",
        "Syntax":"Check the nearby statement and matching delimiters.",
        "Semantic":"Check declarations, assignments, and operand types.",
        "Runtime":"Check the expression and loop condition at this location.",
    }
    def __init__(self, category, line, message, column=1, hint=None):
        self.category,self.line,self.message,self.column=category,line,message,column
        self.hint=hint or self.HINTS.get(category,"Review the source at this location.")
        super().__init__(f"{category} Error (Line {line}): {message}")
    def __str__(self):
        return (f"{self.category} Error (Line {self.line}, Column {self.column}): "
                f"{self.message} Hint: {self.hint}")

class CompilerErrors(CompilerError):
    def __init__(self, errors):
        self.errors=list(errors)
        first=self.errors[0]
        super().__init__(first.category,first.line,f"{len(self.errors)} errors found",first.column,
                         "Resolve the listed diagnostics and compile again.")
    def __str__(self): return "\n".join(str(error) for error in self.errors)

@dataclass
class Token:
    type:str; lexeme:str; line:int; column:int
    def __str__(self): return f"{self.type}\t{self.lexeme}\t{self.line}\t{self.column}"

class Lexer:
    KEYWORDS={"START":"START","END":"END","int":"INT","string":"STRING","print":"PRINT","if":"IF","else":"ELSE","while":"WHILE","mod":"MOD","modulus":"MOD","modulas":"MOD"}
    TWO={"==":"EQ","!=":"NE",">=":"GE","<=":"LE"}
    ONE={"+":"PLUS","-":"MINUS","*":"STAR","/":"SLASH","%":"MOD",">":"GT","<":"LT","=":"ASSIGN","(":"LPAREN",")":"RPAREN","{":"LBRACE","}":"RBRACE",";":"SEMICOLON"}
    def __init__(self,source): self.s=source or ""; self.i=0; self.line=1; self.col=1
    def scan(self):
        out=[]
        while self.i<len(self.s):
            c=self.s[self.i]
            if c in " \r\t": self._adv(); continue
            if c=="\n": self._adv(); continue
            if self.s.startswith("//",self.i):
                while self.i<len(self.s) and self.s[self.i]!="\n": self._adv()
                continue
            ln,cl=self.line,self.col
            if c.isalpha() or c=="_":
                a=self.i
                while self.i<len(self.s) and (self.s[self.i].isalnum() or self.s[self.i]=="_"): self._adv()
                w=self.s[a:self.i];out.append(Token(self.KEYWORDS.get(w,"IDENTIFIER"),w,ln,cl));continue
            if c.isdigit():
                a=self.i
                while self.i<len(self.s) and self.s[self.i].isdigit():self._adv()
                out.append(Token("NUMBER",self.s[a:self.i],ln,cl));continue
            if c=='"':
                self._adv();v=[]
                while self.i<len(self.s) and self.s[self.i]!='"':
                    ch=self.s[self.i]
                    if ch=="\n":raise CompilerError("Lexical",self.line,"Unterminated string literal.",self.col)
                    if ch=="\\":
                        self._adv()
                        if self.i>=len(self.s):
                            raise CompilerError("Lexical",self.line,"Unterminated string literal.",self.col)
                        if self.s[self.i]=="\n":
                            raise CompilerError("Lexical",self.line,"Unterminated string literal.",self.col)
                        esc=self.s[self.i];v.append({"n":"\n","t":"\t",'"':'"',"\\":"\\"}.get(esc,esc));self._adv()
                    else:v.append(ch);self._adv()
                if self.i>=len(self.s):raise CompilerError("Lexical",self.line,"Unterminated string literal.",self.col)
                self._adv();out.append(Token("STRING_LITERAL","".join(v),ln,cl));continue
            pair=self.s[self.i:self.i+2]
            if pair in self.TWO:self._adv();self._adv();out.append(Token(self.TWO[pair],pair,ln,cl));continue
            if c in self.ONE:self._adv();out.append(Token(self.ONE[c],c,ln,cl));continue
            raise CompilerError("Lexical",ln,f"Unknown character '{c}'.",cl)
        out.append(Token("EOF","",self.line,self.col));return out
    def _adv(self):
        ch=self.s[self.i]
        self.i+=1
        if ch=="\n":self.line+=1;self.col=1
        else:self.col+=1

@dataclass
class Expr:
    kind:str; value:object=None; left:object=None; op:str=None; right:object=None; line:int=1; column:int=1
@dataclass
class Stmt:
    kind:str; line:int; name:str=""; typ:str=""; expr:Expr=None; yes:list=field(default_factory=list); no:list=field(default_factory=list); column:int=1

class Parser:
    PRE={"EQ":1,"NE":1,"GT":2,"GE":2,"LT":2,"LE":2,"PLUS":3,"MINUS":3,"STAR":4,"SLASH":4,"MOD":4}
    STARTERS={"INT","STRING","PRINT","IF","WHILE","IDENTIFIER"}
    def __init__(self,tokens):self.ts=tokens;self.p=0;self.errors=[]
    def parse(self):
        self.errors=[]
        if self.match("START"):st=self.prev()
        else:
            st=self.peek()
            self.errors.append(self.err(st,"Expected START at the beginning of the program."))
        body=self._parse_statements({"END","EOF"})
        if self.match("END"):end=self.prev()
        else:
            end=self.peek()
            self.errors.append(self.err(end,"Expected END to close the program."))
        if not self.check("EOF"):
            self.errors.append(self.err(self.peek(),"Unexpected text after END."))
        if self.errors:raise CompilerErrors(self.errors)
        return Stmt("program",st.line,yes=body,column=st.column)

    def _parse_statements(self,stops):
        body=[]
        while self.peek().type not in stops:
            start=self.p
            try:body.append(self.statement())
            except CompilerError as error:
                self.errors.append(error)
                self._synchronize(start)
            if self.p==start and self.peek().type not in stops and not self.check("EOF"):self.adv()
        return body

    def _synchronize(self,start):
        while not self.check("EOF") and not self.check("END") and not self.check("RBRACE"):
            if self.p>start and self.prev().type=="SEMICOLON":return
            if self.peek().type in self.STARTERS:return
            self.adv()

    def statement(self):
        if self.match("INT","STRING"):return self.decl(self.prev())
        if self.match("PRINT"):return self.print_stmt(self.prev())
        if self.match("IF"):return self.if_stmt(self.prev())
        if self.match("WHILE"):return self.while_stmt(self.prev())
        if self.match("IDENTIFIER"):return self.assign(self.prev())
        raise self.err(self.peek(),"Expected a declaration, assignment, print, if, or while statement.")
    def decl(self,t):
        n=self.take("IDENTIFIER","Expected a variable name after type.");e=self.expression() if self.match("ASSIGN") else None
        self.take("SEMICOLON","Expected semicolon after declaration.");return Stmt("decl",t.line,n.lexeme,"int" if t.type=="INT" else "string",e,column=t.column)
    def assign(self,t):
        self.take("ASSIGN","Expected '=' after variable name.");e=self.expression();self.take("SEMICOLON","Expected semicolon after assignment.");return Stmt("assign",t.line,t.lexeme,expr=e,column=t.column)
    def print_stmt(self,t):
        self.take("LPAREN","Expected '(' after print.");e=self.expression();self.take("RPAREN","Expected ')' after print value.");self.take("SEMICOLON","Expected semicolon after print.");return Stmt("print",t.line,expr=e,column=t.column)
    def if_stmt(self,t):
        self.take("LPAREN","Expected '(' after if.");e=self.expression();self.take("RPAREN","Expected ')' after condition.");y=self.block();n=self.block() if self.match("ELSE") else [];return Stmt("if",t.line,expr=e,yes=y,no=n,column=t.column)
    def while_stmt(self,t):
        self.take("LPAREN","Expected '(' after while.");e=self.expression();self.take("RPAREN","Expected ')' after condition.");return Stmt("while",t.line,expr=e,yes=self.block(),column=t.column)
    def block(self):
        self.take("LBRACE","Expected '{' to start block.")
        body=self._parse_statements({"RBRACE","EOF","END"})
        if self.match("RBRACE"):return body
        self.errors.append(self.err(self.peek(),"Expected '}' to close block."))
        return body
    def expression(self):return self.binary(0)
    def binary(self,minp):
        e=self.unary()
        while self.peek().type in self.PRE and self.PRE[self.peek().type]>=minp:
            op=self.adv();e=Expr("binary",left=e,op=op.type,right=self.binary(self.PRE[op.type]+1),line=op.line,column=op.column)
        return e
    def unary(self):
        if self.match("MINUS"):t=self.prev();return Expr("unary",op="MINUS",right=self.unary(),line=t.line,column=t.column)
        return self.primary()
    def primary(self):
        if self.match("NUMBER"):t=self.prev();return Expr("literal",int(t.lexeme),line=t.line,column=t.column)
        if self.match("STRING_LITERAL"):t=self.prev();return Expr("literal",t.lexeme,line=t.line,column=t.column)
        if self.match("IDENTIFIER"):t=self.prev();return Expr("variable",t.lexeme,line=t.line,column=t.column)
        if self.match("LPAREN"):e=self.expression();self.take("RPAREN","Expected ')' after expression.");return e
        raise self.err(self.peek(),"Expected a number, string, variable, or parenthesized expression.")
    def match(self,*ts):
        if self.peek().type in ts:self.adv();return True
        return False
    def take(self,t,msg):
        if self.check(t):return self.adv()
        raise self.err(self.peek(),msg)
    def check(self,t):return self.peek().type==t
    def adv(self):
        if not self.check("EOF"):self.p+=1
        return self.prev()
    def peek(self):return self.ts[self.p]
    def prev(self):return self.ts[self.p-1]
    def err(self,t,m):return CompilerError("Syntax",t.line,m,t.column)

class SemanticAnalyzer:
    _NOT_CONSTANT=object()
    def __init__(self):
        self.symbols=OrderedDict();self.initialized=set();self.errors=[];self.declarations={}
    def analyze(self,p):
        self.symbols=OrderedDict();self.initialized=set();self.errors=[];self.declarations={}
        for s in p.yes:self._check_safe(s)
        if self.errors:raise CompilerErrors(self.errors)
        return self.symbols
    def _check_safe(self,s):
        try:self.check(s)
        except CompilerError as error:self.errors.append(error)
    def _error(self,node,message):
        return CompilerError("Semantic",node.line,message,getattr(node,"column",1))
    def check(self,s):
        if s.kind=="decl":
            if s.name in self.symbols:raise self._error(s,f"Variable '{s.name}' is already declared.")
            if s.expr:
                actual=self.typ(s.expr)
                if actual!=s.typ:raise self._error(s,f"Cannot assign {actual} to {s.typ} variable '{s.name}'.")
            self.symbols[s.name]={"type":s.typ,"value":None}
            self.declarations[s.name]=(s.line,s.column)
            if s.expr:self.initialized.add(s.name)
        elif s.kind=="assign":
            if s.name not in self.symbols:raise self._error(s,f"Variable '{s.name}' is not declared.")
            actual=self.typ(s.expr)
            if actual!=self.symbols[s.name]["type"]:raise self._error(s,f"Cannot assign {actual} to {self.symbols[s.name]['type']} variable '{s.name}'.")
            self.initialized.add(s.name)
        elif s.kind=="print":self.typ(s.expr)
        elif s.kind in ("if","while"):
            try:
                if self.typ(s.expr)!="bool":raise self._error(s.expr,"Condition must use a comparison operator.")
            except CompilerError as error:self.errors.append(error)
            before=self.initialized.copy()
            for x in s.yes:self._check_safe(x)
            yes=self.initialized.copy()
            if s.kind=="if":
                self.initialized=before.copy()
                for x in s.no:self._check_safe(x)
                no=self.initialized.copy()
                self.initialized=(yes & no) if s.no else (before & yes)
            else:self.initialized=before
    def typ(self,e):
        if e.kind=="literal":return "int" if isinstance(e.value,int) else "string"
        if e.kind=="variable":
            if e.value not in self.symbols:raise self._error(e,f"Variable '{e.value}' is not declared.")
            if e.value not in self.initialized:raise self._error(e,f"Variable '{e.value}' may be used before assignment.")
            return self.symbols[e.value]["type"]
        if e.kind=="unary":
            if self.typ(e.right)!="int":raise self._error(e,"Unary '-' requires an integer.")
            return "int"
        a,b=self.typ(e.left),self.typ(e.right)
        if e.op in ("PLUS","MINUS","STAR","SLASH","MOD"):
            if a!="int" or b!="int":raise self._error(e,"Arithmetic operators require integer operands.")
            if e.op in ("SLASH","MOD") and self._constant(e.right)==0:
                raise self._error(e,"Modulus by zero in constant expression." if e.op=="MOD" else "Division by zero in constant expression.")
            return "int"
        if e.op in ("EQ","NE"):
            if a!=b:raise self._error(e,"Comparison operands must have the same type.")
            return "bool"
        if a!="int" or b!="int":raise self._error(e,"Ordered comparisons require integer operands.")
        return "bool"
    def _constant(self,e):
        if e.kind=="literal":return e.value
        if e.kind=="variable":return self._NOT_CONSTANT
        if e.kind=="unary":
            value=self._constant(e.right)
            return -value if value is not self._NOT_CONSTANT else value
        left,right=self._constant(e.left),self._constant(e.right)
        if left is self._NOT_CONSTANT or right is self._NOT_CONSTANT:return self._NOT_CONSTANT
        try:
            return {
                "PLUS":lambda:left+right,"MINUS":lambda:left-right,
                "STAR":lambda:left*right,"SLASH":lambda:int(left/right),"MOD":lambda:left-int(left/right)*right,
            }.get(e.op,lambda:self._NOT_CONSTANT)()
        except (ArithmeticError,TypeError):
            return self._NOT_CONSTANT

OPS={"PLUS":"+","MINUS":"-","STAR":"*","SLASH":"/","MOD":"%","EQ":"==","NE":"!=","GT":">","GE":">=","LT":"<","LE":"<="}
def extext(e):
    if e.kind=="literal":return json.dumps(e.value,ensure_ascii=False) if isinstance(e.value,str) else str(e.value)
    if e.kind=="variable":return e.value
    if e.kind=="unary":return "-"+extext(e.right)
    return f"({extext(e.left)} {OPS[e.op]} {extext(e.right)})"
def ast_text(p):
    out=["Program"]
    def walk(s,d):
        pad="  "*d
        if s.kind=="decl":out.append(pad+f"Declaration {s.typ} {s.name}"+(f" = {extext(s.expr)}" if s.expr else ""))
        elif s.kind=="assign":out.append(pad+f"Assignment {s.name} = {extext(s.expr)}")
        elif s.kind=="print":out.append(pad+f"Print {extext(s.expr)}")
        else:
            out.append(pad+f"{s.kind.title()} {extext(s.expr)}")
            for x in s.yes:walk(x,d+1)
            if s.no:
                out.append(pad+"  Else")
                for x in s.no:walk(x,d+2)
    for s in p.yes:walk(s,1)
    return "\n".join(out)
class CodeGenerator:
    def generate(self,p):
        self.out=[];self.source_map=[];self.temp=0;self.label=0;self.current_line=None
        for s in p.yes:self.stmt(s)
        return "\n".join(self.out)+("\n" if self.out else "")
    def _emit(self,line):
        self.out.append(line)
        self.source_map.append(self.current_line)
    def stmt(self,s):
        self.current_line=s.line
        if s.kind=="decl":
            if s.expr:self._emit(f"{s.name} = {self.expr(s.expr)}")
        elif s.kind=="assign":self._emit(f"{s.name} = {self.expr(s.expr)}")
        elif s.kind=="print":self._emit("PRINT "+self.expr(s.expr))
        elif s.kind=="if":
            self.label+=1;els=f"L{self.label}";self.label+=1;end=f"L{self.label}"
            self._emit(f"IF_FALSE {self.expr(s.expr)} GOTO {els}")
            for x in s.yes:self.stmt(x)
            if s.no:
                self.current_line=s.line
                self._emit(f"GOTO {end}")
            self.current_line=s.line
            self._emit(els+":")
            for x in s.no:self.stmt(x)
            if s.no:
                self.current_line=s.line
                self._emit(end+":")
        elif s.kind=="while":
            self.label+=1;begin=f"L{self.label}";self.label+=1;end=f"L{self.label}"
            condition = self.expr(s.expr)
            self.current_line=s.line
            self._emit(begin+":")
            self._emit(f"IF_FALSE {condition} GOTO {end}")
            for x in s.yes:self.stmt(x)
            self.current_line=s.line
            self._emit(f"GOTO {begin}")
            self._emit(end+":")
    def expr(self,e):
        if e.kind=="literal":return json.dumps(e.value,ensure_ascii=False) if isinstance(e.value,str) else str(e.value)
        if e.kind=="variable":return e.value
        if e.kind=="unary":
            v=self.expr(e.right);self.temp+=1;t=f"t{self.temp}";self._emit(f"{t} = -{v}");return t
        a=self.expr(e.left);b=self.expr(e.right);self.temp+=1;t=f"t{self.temp}";self._emit(f"{t} = {a} {OPS[e.op]} {b}");return t

class Interpreter:
    def __init__(self,hook=None,stop=None,timeout=10.0):
        self.values={};self.output=[];self.steps=0;self.hook=hook;self.stop=stop
        self.timeout=timeout;self.started_at=None
    def run(self,p):
        self.started_at=time.monotonic()
        for s in p.yes:self.exec(s)
        return "\n".join(map(str,self.output))+("\n" if self.output else "")
    def tick(self,line,column=1):
        self.steps+=1
        if self.stop and self.stop.is_set():raise CompilerError("Runtime",line,"Execution stopped by the user.",column)
        if self.steps>100000:raise CompilerError("Runtime",line,"Execution limit exceeded (possible infinite loop).",column)
        if self.timeout is not None and self.started_at is not None and time.monotonic()-self.started_at>self.timeout:
            raise CompilerError("Runtime",line,"Execution time limit exceeded.",column)
    def exec(self,s):
        if self.hook:self.hook(s,self.values)
        self.tick(s.line,s.column)
        if s.kind=="decl":
            if s.expr:self.values[s.name]=self.eval(s.expr)
        elif s.kind=="assign":self.values[s.name]=self.eval(s.expr)
        elif s.kind=="print":self.output.append(self.eval(s.expr))
        elif s.kind=="if":
            for x in (s.yes if self.eval(s.expr) else s.no):self.exec(x)
        elif s.kind=="while":
            while self.eval(s.expr):
                self.tick(s.line,s.column)
                for x in s.yes:self.exec(x)
    def eval(self,e):
        if e.kind=="literal":return e.value
        if e.kind=="variable":
            if e.value not in self.values:raise CompilerError("Runtime",e.line,f"Variable '{e.value}' has no value.",e.column)
            return self.values[e.value]
        if e.kind=="unary":return -self.eval(e.right)
        a,b=self.eval(e.left),self.eval(e.right)
        if e.op=="PLUS":return a+b
        if e.op=="MINUS":return a-b
        if e.op=="STAR":return a*b
        if e.op=="SLASH":
            if b==0:raise CompilerError("Runtime",e.line,"Division by zero.",e.column)
            return int(a/b)
        if e.op=="MOD":
            if b==0:raise CompilerError("Runtime",e.line,"Modulus by zero.",e.column)
            return a-int(a/b)*b
        return {"EQ":lambda:a==b,"NE":lambda:a!=b,"GT":lambda:a>b,"GE":lambda:a>=b,"LT":lambda:a<b,"LE":lambda:a<=b}[e.op]()

# ============================ Grammar algorithms ===========================
EPS="ε"; END="$"
def tokenize_symbols(s):
    s=s.strip()
    if s.lower() in (EPS,"epsilon","eps","~"):return [EPS]
    if re.search(r"\s",s):
        a=s.split()
        if EPS in a and len(a)!=1:raise ValueError("Epsilon must be the only symbol in an alternative.")
        return a
    if s in ("id","number") or re.fullmatch(r"[A-Z][A-Za-z0-9_']*|[a-z]+[0-9]+|[0-9]+",s):return [s]
    out=[];i=0
    while i<len(s):
        c=s[i]
        if c.isupper() or c=="_":
            j=i+1
            while j<len(s) and (s[j].isalnum() or s[j] in "_'"):j+=1
            out.append(s[i:j]);i=j
        elif c.islower():
            j=i+1
            while j<len(s) and s[j].islower():j+=1
            word=s[i:j]
            out.extend([word] if word in ("id","number") else list(word));i=j
        elif c.isdigit():
            j=i+1
            while j<len(s) and s[j].isdigit():j+=1
            out.append(s[i:j]);i=j
        else:out.append(c);i+=1
    return out
class Grammar:
    def __init__(self):self.rules=OrderedDict();self.start=None
    @classmethod
    def parse(cls,text):
        g=cls()
        for row,line in enumerate(text.splitlines(),1):
            line=line.strip()
            if not line or line.startswith("#"):continue
            m=re.search(r"->|→",line)
            if not m:raise ValueError(f"Line {row}: expected '->'.")
            lhs=line[:m.start()].strip();rhs=line[m.end():].strip()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_']*",lhs):raise ValueError(f"Line {row}: invalid non-terminal '{lhs}'.")
            if not rhs:raise ValueError(f"Line {row}: use ε for an empty production.")
            if g.start is None:g.start=lhs
            for alt in rhs.split("|"):
                if not alt.strip():raise ValueError(f"Line {row}: empty alternative; write ε explicitly.")
                g.rules.setdefault(lhs,[]).append(tokenize_symbols(alt))
        if not g.rules:raise ValueError("Enter at least one production rule.")
        for alts in g.rules.values():
            for r in alts:
                for x in r:
                    if re.fullmatch(r"[A-Z][A-Za-z0-9_']*",x) and x not in g.rules:raise ValueError(f"Undefined non-terminal '{x}'.")
        return g
    def copy(self):
        g=Grammar();g.start=self.start;g.rules=OrderedDict((k,[r[:] for r in v]) for k,v in self.rules.items());return g
    def terminals(self):return {x for a in self.rules.values() for r in a for x in r if x!=EPS and x not in self.rules}
    def format(self):return "\n".join(k+" -> "+" | ".join(" ".join(r) if r else EPS for r in v) for k,v in self.rules.items())+"\n"
class FirstFollow:
    def __init__(self,g):
        self.g=g;self.first={n:set() for n in g.rules};self.follow={n:set() for n in g.rules};self.calculate()
    def firstseq(self,seq):
        if not seq:return {EPS}
        out=set();nullable=True
        for s in seq:
            f=self.first[s] if s in self.g.rules else {s};out|=f-{EPS}
            if EPS not in f:nullable=False;break
        if nullable:out.add(EPS)
        return out
    def calculate(self):
        changed=True
        while changed:
            changed=False
            for n,alts in self.g.rules.items():
                old=len(self.first[n])
                for r in alts:self.first[n]|=self.firstseq(r)
                changed|=len(self.first[n])!=old
        self.follow[self.g.start].add(END);changed=True
        while changed:
            changed=False
            for n,alts in self.g.rules.items():
                for r in alts:
                    for i,x in enumerate(r):
                        if x not in self.g.rules:continue
                        f=self.firstseq(r[i+1:]);old=len(self.follow[x]);self.follow[x]|=f-{EPS}
                        if not r[i+1:] or EPS in f:self.follow[x]|=self.follow[n]
                        changed|=len(self.follow[x])!=old
class LL1Table:
    def __init__(self,g):
        self.g=g;self.ff=FirstFollow(g);self.cells={n:{} for n in g.rules};self.conflicts=[]
        for n,alts in g.rules.items():
            for r in alts:
                f=self.ff.firstseq(r);targets=(f-{EPS})|(self.ff.follow[n] if EPS in f else set())
                for t in targets:
                    old=self.cells[n].setdefault(t,[])
                    if old and r not in old:self.conflicts.append(f"Conflict at M[{n}, {t}]: {old[0]} versus {r}")
                    if r not in old:old.append(r)
    def text(self):
        ts=sorted(self.g.terminals()|{END});out=["NT\t"+"\t".join(ts)]
        for n in self.g.rules:out.append(n+"\t"+"\t".join(" | ".join(" ".join(r) or EPS for r in self.cells[n].get(t,[])) for t in ts))
        return "\n".join(out)
def predictive_parse(table,source):
    if table.conflicts:raise ValueError("Predictive parsing needs an LL(1) grammar.")
    inp=tokenize_symbols(source) if source.strip() else [];inp.append(END);stack=[END,table.g.start];trace=[];pos=0
    for _ in range(10000):
        top=stack[-1];look=inp[pos];old=" ".join(reversed(stack));rest=" ".join(inp[pos:])
        if top==END and look==END:trace.append((old,rest,"Accept"));return True,trace,"Input accepted."
        if top==look:stack.pop();pos+=1;trace.append((old,rest,"Match "+look));continue
        if top in table.g.rules:
            choices=table.cells[top].get(look)
            if not choices:trace.append((old,rest,f"Error: no entry [{top}, {look}]"));return False,trace,"Rejected: no production."
            r=choices[0];stack.pop()
            if r!=[EPS]:stack.extend(reversed(r))
            trace.append((old,rest,top+" -> "+" ".join(r)))
        else:trace.append((old,rest,"Error: expected "+top));return False,trace,"Rejected: expected "+top
    return False,trace,"Rejected: parser step limit exceeded."
def remove_left_recursion(inp):
    g=inp.copy();order=list(g.rules)
    for i,ai in enumerate(order):
        expanded=[r[:] for r in g.rules[ai]]
        for aj in order[:i]:
            nxt=[]
            for r in expanded:
                if r and r[0]==aj:
                    for d in g.rules[aj]:nxt.append(d+r[1:])
                else:nxt.append(r)
            expanded=nxt
            if len(expanded)>5000:raise ValueError("Transformation expanded beyond 5,000 alternatives.")
        alpha=[r[1:] for r in expanded if r and r[0]==ai];beta=[r for r in expanded if not(r and r[0]==ai)]
        if not alpha:g.rules[ai]=expanded;continue
        if any(not r for r in alpha):raise ValueError(f"Production {ai} -> {ai} cannot be removed.")
        if not beta:raise ValueError(f"{ai} has left recursion but no non-recursive alternative.")
        fresh=ai+"'"
        while fresh in g.rules:fresh+="'"
        g.rules[ai]=[r+[fresh] for r in beta];g.rules[fresh]=[r+[fresh] for r in alpha]+[[EPS]];order.append(fresh)
    return g
def left_factor(inp):
    g=inp.copy();rounds=0
    while True:
        rounds+=1
        if rounds>1000:raise ValueError("Factoring exceeded 1,000 transformations.")
        changed=False
        for n in list(g.rules):
            alts=g.rules[n];best=[]
            for i in range(len(alts)):
                for j in range(i+1,len(alts)):
                    k=0
                    while k<min(len(alts[i]),len(alts[j])) and alts[i][k]==alts[j][k]:k+=1
                    if k>len(best):best=alts[i][:k]
            if not best:continue
            fresh=n+"'"
            while fresh in g.rules:fresh+="'"
            remain=[];suffix=[];inserted=False
            for r in alts:
                if r[:len(best)]==best:
                    if not inserted:remain.append(best+[fresh]);inserted=True
                    tail=r[len(best):] or [EPS]
                    if tail not in suffix:suffix.append(tail)
                elif r not in remain:remain.append(r)
            g.rules[n]=remain;g.rules[fresh]=suffix;changed=True;break
        if not changed:return g
def shift_reduce_parse(g,source):
    inp=tokenize_symbols(source);q=deque([((),0,[])]);seen=set();work=0
    while q and work<30000:
        stack,pos,tr=q.popleft();work+=1
        if (stack,pos) in seen:continue
        seen.add((stack,pos))
        if pos==len(inp) and stack==(g.start,):return True,tr+["Accept"],"Input accepted by a shift/reduce path."
        if pos<len(inp):q.append((stack+(inp[pos],),pos+1,tr+["Shift "+inp[pos]]))
        for n,alts in g.rules.items():
            for r in alts:
                body=() if r==[EPS] else tuple(r)
                if body and len(stack)>=len(body) and stack[-len(body):]==body:q.append((stack[:-len(body)]+(n,),pos,tr+[f"Reduce {n} -> {' '.join(r)}"]))
    return False,[], "Rejected or configuration limit reached. The simulator does not resolve ambiguity."
def slr_report(g):
    ff=FirstFollow(g);nts=list(g.rules);aug=g.start+"'"
    while aug in g.rules:aug+="'"
    owners=[aug];prods=[(g.start,)]
    for n,alts in g.rules.items():
        for r in alts:owners.append(n);prods.append(tuple() if r==[EPS] else tuple(r))
    def closure(seed):
        out=set(seed);changed=True
        while changed:
            changed=False
            for p,d in list(out):
                if d<len(prods[p]):
                    x=prods[p][d]
                    if x in g.rules:
                        for i,o in enumerate(owners):
                            if o==x and (i,0) not in out:out.add((i,0));changed=True
        return frozenset(out)
    states=[closure({(0,0)})];trans={}
    for i,I in enumerate(states):
        syms=[]
        for p,d in I:
            if d<len(prods[p]) and prods[p][d] not in syms:syms.append(prods[p][d])
        for x in syms:
            J=closure({(p,d+1) for p,d in I if d<len(prods[p]) and prods[p][d]==x})
            if J not in states:states.append(J)
            trans[i,x]=states.index(J)
    actions={i:{} for i in range(len(states))};gotos={i:{} for i in range(len(states))};conf=[];terms=sorted(g.terminals()|{END})
    def put(i,x,v):
        if x in actions[i] and actions[i][x]!=v:conf.append(f"State {i}, {x}: {actions[i][x]} / {v}")
        else:actions[i][x]=v
    for i,I in enumerate(states):
        for p,d in I:
            if d<len(prods[p]):
                x=prods[p][d];target=trans[i,x]
                if x in g.rules:gotos[i][x]=target
                else:put(i,x,"s"+str(target))
            elif p==0:put(i,END,"accept")
            else:
                for x in ff.follow[owners[p]]:put(i,x,"r"+str(p))
    out=["LR(0) ITEM SETS"]
    for i,I in enumerate(states):
        out.append(f"I{i}:")
        for p,d in sorted(I):
            r=list(prods[p]);r.insert(d,"·");out.append(f"  {owners[p]} -> {' '.join(r) or '·'}")
    out.append("\nSLR ACTION/GOTO TABLE\nSTATE\t"+"\t".join(terms)+"\t|\t"+"\t".join(nts))
    for i in range(len(states)):out.append(str(i)+"\t"+"\t".join(actions[i].get(t,"") for t in terms)+"\t|\t"+"\t".join(str(gotos[i].get(n,"")) for n in nts))
    out.append("\n"+("\n".join(conf) if conf else "No SLR conflicts."))
    return "\n".join(out)

# ================================ C++ runner ================================
def cpp_run(source_path,stdin_text=""):
    compiler=os.environ.get("EASYLANG_GXX") or shutil.which("g++")
    if not compiler:raise RuntimeError("GCC g++ not found. Install GCC or set EASYLANG_GXX.")
    source=Path(source_path);build=source.parent/"build"/"cpp";build.mkdir(parents=True,exist_ok=True)
    exe=build/(source.stem+(".exe" if os.name=="nt" else ""))
    c=subprocess.run([compiler,"-std=c++17",str(source),"-o",str(exe)],capture_output=True,text=True,timeout=30)
    if c.returncode:return "Compilation failed:\n"+c.stderr
    try:
        r=subprocess.run([str(exe)],input=stdin_text,capture_output=True,text=True,timeout=10)
        return r.stdout+r.stderr
    except subprocess.TimeoutExpired:return "Execution stopped: 10-second time limit exceeded."

class AutoCorrector:
    """Conservative, preview-first source corrections for known EasyLang patterns.

    Suggestions are intentionally limited to mechanical edits whose intent is clear.
    Semantic/runtime problems that require guessing a value or declaration are not
    rewritten automatically.
    """
    KEYWORD_FIXES = {
        "prit": "print", "prnt": "print", "pirnt": "print", "pritn": "print",
        "whlie": "while", "wile": "while", "els": "else", "elze": "else",
        "strng": "string", "sring": "string", "stirng": "string",
        "flot": "float", "flotat": "float", "bol": "bool", "bln": "bool",
        "interger": "int", "integar": "int", "intr": "int",
        "modulas": "mod", "modulus": "mod",
    }

    def __init__(self, source):
        self.original = source or ""
        self.source = self.original
        self.history = []

    @staticmethod
    def _has_program_marker(rows, marker):
        return any(row.strip() == marker for row in rows)

    def suggestions(self):
        rows = self.source.splitlines()
        found = []

        # START/END are required by the existing EasyLang grammar. Insert only
        # when the exact standalone marker is absent; comments may precede START.
        if not self._has_program_marker(rows, "START"):
            found.append((1, "Insert missing START", "START"))
        if not self._has_program_marker(rows, "END"):
            found.append((len(rows) + 1, "Insert missing END", "END"))

        for index, line in enumerate(rows, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//") or stripped in ("START", "END"):
                continue

            updated = line
            # Correct only known misspellings when they appear as a statement
            # keyword at the start of a line; never rewrite string contents.
            # Correct recognized typos in code, including expression operators
            # such as modulas, while protecting quoted literals and comments.
            parts = re.split(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')', updated)
            changed_typos = []
            for part_index in range(0, len(parts), 2):
                code = parts[part_index]
                for typo, replacement in self.KEYWORD_FIXES.items():
                    if re.search(r"\b" + re.escape(typo) + r"\b", code):
                        code = re.sub(r"\b" + re.escape(typo) + r"\b", replacement, code)
                        changed_typos.append((typo, replacement))
                parts[part_index] = code
            corrected_line = "".join(parts)
            if changed_typos:
                updated = corrected_line
                names = "; ".join(f"{typo} -> {replacement}" for typo, replacement in changed_typos)
                found.append((index, f"Correct recognized keyword/modulus typo: {names}", updated))

            # Add missing opening braces to block headers when the next line is a
            # statement and the header has no brace. This directly repairs common
            # if/else and while examples without guessing expression contents.
            block_header = re.match(r"^(\s*)(if|while)\s*\(.+\)\s*$", updated)
            if block_header and not updated.rstrip().endswith("{"):
                updated = updated.rstrip() + " {"
                found.append((index, "Add missing opening brace to control block", updated))
            elif re.match(r"^\s*else\s*$", updated) and not updated.rstrip().endswith("{"):
                updated = updated.rstrip() + " {"
                found.append((index, "Add missing opening brace to else block", updated))

            # Add a semicolon only to complete, single-line statement forms.
            # Control-flow headers, braces, comments, and incomplete expressions
            # are deliberately excluded to avoid changing program structure.
            candidate = updated.strip()
            statement = (
                re.fullmatch(r"(?:int|string)\s+[A-Za-z_]\w*(?:\s*=\s*.+)?", candidate)
                or re.fullmatch(r"[A-Za-z_]\w*\s*=\s*.+", candidate)
                or re.fullmatch(r"print\s*\(.+\)", candidate)
            )
            if statement and not candidate.endswith(";"):
                updated = updated.rstrip() + ";" + updated[len(updated.rstrip()):]
                found.append((index, "Add missing semicolon", updated))


        # A missing closing brace is a mechanical repair only when the real
        # lexer can tokenize the file and the opening/closing counts prove it.
        try:
            tokens = Lexer(self.source).scan()
            missing_braces = sum(token.type == "LBRACE" for token in tokens) - sum(
                token.type == "RBRACE" for token in tokens
            )
            if missing_braces > 0:
                end_line = next((i for i, row in enumerate(rows, 1) if row.strip() == "END"), len(rows) + 1)
                found.extend((end_line, "Insert missing '}' before END", "}") for _ in range(missing_braces))
        except CompilerError as lex_error:
            if "Unterminated string literal" in getattr(lex_error, "message", ""):
                line_no = getattr(lex_error, "line", 0)
                if 1 <= line_no <= len(rows):
                    line = rows[line_no - 1]
                    quote_count = 0
                    escaped = False
                    for char in line:
                        if char == '"' and not escaped:
                            quote_count += 1
                        if char == "\\" and not escaped:
                            escaped = True
                        else:
                            escaped = False
                    if quote_count % 2:
                        found.append((line_no, "Insert missing closing quote", line.rstrip() + '"'))

        # Merge multiple safe edits on one line (for example a typo and a
        # missing semicolon) into one final replacement.
        merged = {}
        for line_no, description, replacement in found:
            if description.startswith("Insert missing"):
                continue
            merged[line_no] = replacement
        result = []
        seen = set()
        for line_no, description, replacement in found:
            if description.startswith("Insert missing"):
                result.append((line_no, description, replacement))
            elif line_no not in seen:
                result.append((line_no, "; ".join(
                    item[1] for item in found
                    if item[0] == line_no and not item[1].startswith("Insert missing")
                ), merged[line_no]))
                seen.add(line_no)
        return result

    def suggestions_for_error(self, error):
        """Return only mechanical suggestions relevant to a compiler diagnostic."""
        errors = getattr(error, "errors", [error])
        all_fixes = self.suggestions()
        selected = []
        for diagnostic in errors:
            message = getattr(diagnostic, "message", str(diagnostic))
            line = getattr(diagnostic, "line", None)
            candidates = []
            for fix in all_fixes:
                fix_line, description, _replacement = fix
                if description.startswith("Insert missing") or (line is not None and fix_line == line):
                    candidates.append(fix)
            if "semicolon" in message.lower() and line is not None:
                prior = [fix for fix in all_fixes if fix[0] <= line and "semicolon" in fix[1].lower()]
                if prior:
                    nearest = max(fix[0] for fix in prior)
                    candidates.extend(fix for fix in prior if fix[0] == nearest)
            for fix in candidates:
                if fix not in selected:
                    selected.append(fix)
        return selected

    def apply(self, lines=None):
        fixes = self.suggestions()
        selected = set(lines if lines is not None else [item[0] for item in fixes])
        rows = self.source.splitlines()
        self.history.append(self.source)

        # Replace ordinary source lines first, preserving one edit per line.
        replacements = {}
        insert_start = False
        insert_end = False
        for line_no, description, replacement in fixes:
            if line_no not in selected:
                continue
            if description == "Insert missing START":
                insert_start = True
            elif description == "Insert missing END":
                insert_end = True
            elif description == "Insert missing '}' before END":
                rows.insert(max(0, min(line_no - 1, len(rows))), replacement)
            elif 1 <= line_no <= len(rows):
                replacements[line_no] = replacement
        for line_no, replacement in replacements.items():
            rows[line_no - 1] = replacement
        if insert_start:
            rows.insert(0, "START")
        if insert_end:
            rows.append("END")
        self.source = "\n".join(rows) + ("\n" if self.source.endswith("\n") else "")
        return self.source

    def undo(self):
        if self.history:
            self.source = self.history.pop()
        return self.source

    def restore(self):
        self.source = self.original
        self.history.clear()
        return self.source

SAMPLE="START\n// EasyLang sample\nint age = 20;\nstring name = \"Ali\";\nif (age > 18) {\n    print(\"Hello, \");\n    print(name);\n} else {\n    print(\"Minor\");\n}\nEND\n"

# ============================== Desktop application =========================
class EasyLangStudio(tk.Tk):
    def __init__(self):
        super().__init__();self.title("EasyLang Studio — Python Edition");self.geometry("1360x800");self.minsize(1000,650)
        self.dark=True;self.docs={};self.debug_stop=threading.Event();self._theme();self._menu();self._ui();self.new_tab("Untitled-1",SAMPLE)
        self.protocol("WM_DELETE_WINDOW",self.destroy)
    def _theme(self):
        self.bg="#181b22" if self.dark else "#eef1f6";self.panel="#20242d" if self.dark else "#ffffff";self.fg="#e2e8f0" if self.dark else "#202938";self.muted="#9aa8bb"
        self.configure(bg=self.bg);s=ttk.Style(self);s.theme_use("clam")
        s.configure(".",background=self.bg,foreground=self.fg,fieldbackground=self.panel)
        s.configure("TFrame",background=self.bg);s.configure("TLabel",background=self.bg,foreground=self.fg)
        s.configure("TButton",padding=6);s.configure("TNotebook",background=self.bg);s.configure("TNotebook.Tab",padding=(12,7))
        s.configure("Treeview",background=self.panel,foreground=self.fg,fieldbackground=self.panel)
    def _menu(self):
        m=tk.Menu(self);self.config(menu=m)
        f=tk.Menu(m,tearoff=False);m.add_cascade(label="File",menu=f)
        for label,fn in [("New",self.new_file),("Open",self.open_file),("Save",self.save_file),("Save As",self.save_as),("Close Tab",self.close_tab),("Exit",self.destroy)]:f.add_command(label=label,command=fn)
        e=tk.Menu(m,tearoff=False);m.add_cascade(label="Edit",menu=e)
        e.add_command(label="Undo",command=lambda:self.editor.event_generate("<<Undo>>"));e.add_command(label="Redo",command=lambda:self.editor.event_generate("<<Redo>>"));e.add_command(label="Find",command=self.find);e.add_command(label="Replace",command=self.replace)
        v=tk.Menu(m,tearoff=False);m.add_cascade(label="View",menu=v);v.add_command(label="Toggle Theme",command=self.toggle_theme)
        t=tk.Menu(m,tearoff=False);m.add_cascade(label="Tools",menu=t);t.add_command(label="Auto Correction",command=self.auto_correct);t.add_command(label="Advanced Compiler Construction Tools",command=lambda:self.nb.select(self.advanced))
        for seq,fn in [("<Control-n>",self.new_file),("<Control-o>",self.open_file),("<Control-s>",self.save_file),("<Control-Shift-S>",self.save_as),("<Control-w>",self.close_tab)]:self.bind_all(seq,lambda e,f=fn:f())
    def _ui(self):
        bar=ttk.Frame(self);bar.pack(fill="x",padx=8,pady=6)
        for label,fn in [("New",self.new_file),("Open",self.open_file),("Save",self.save_file),("Compile",lambda:self.compile(False)),("Run",lambda:self.compile(True)),("Start Debugging",self.debug),("Auto Correction",self.auto_correct),("Theme",self.toggle_theme)]:
            ttk.Button(bar,text=label,command=fn).pack(side="left",padx=2)
        self.language=tk.StringVar(value="EasyLang");ttk.Label(bar,text="Language:").pack(side="left",padx=(12,3));ttk.Combobox(bar,textvariable=self.language,values=["EasyLang","C++17"],state="readonly",width=10).pack(side="left")
        self.nb=ttk.Notebook(self);self.nb.pack(fill="both",expand=True,padx=8,pady=8)
        self.main=ttk.Frame(self.nb);self.advanced=ttk.Frame(self.nb);self.nb.add(self.main,text="Main Compiler");self.nb.add(self.advanced,text="Advanced Compiler Construction Tools")
        self._main_ui();self._advanced_ui()
    def _main_ui(self):
        split=ttk.Panedwindow(self.main,orient="horizontal");split.pack(fill="both",expand=True)
        left=ttk.Frame(split);right=ttk.Frame(split);split.add(left,weight=5);split.add(right,weight=5)
        ttk.Label(left,text="SOURCE EDITOR",font=("Segoe UI",10,"bold")).pack(anchor="w",padx=5,pady=5)
        self.files=ttk.Notebook(left);self.files.pack(fill="both",expand=True);self.files.bind("<<NotebookTabChanged>>",self._changed)
        self.results=ttk.Notebook(right);self.results.pack(fill="both",expand=True);self.views={}
        for name in ["Tokens","AST","Symbol Table","Three Address Code","Output","Errors","Debugger"]:
            frame=ttk.Frame(self.results);self.results.add(frame,text=name)
            w=tk.Text(frame,wrap="none",font=("Consolas",11),bg=self.panel,fg=self.fg,insertbackground=self.fg);w.pack(fill="both",expand=True);w.configure(state="disabled");self.views[name]=w
        self.status=tk.StringVar(value="Ready");ttk.Label(self.main,textvariable=self.status,anchor="w").pack(fill="x",padx=5,pady=4)
    def new_tab(self,name,content=""):
        frame=ttk.Frame(self.files);g=tk.Text(frame,width=4,state="disabled",font=("Consolas",12),bg=self.bg,fg=self.muted,relief="flat")
        ed=tk.Text(frame,wrap="none",undo=True,font=("Consolas",12),bg=self.panel,fg=self.fg,insertbackground=self.fg,tabs=4)
        sy=ttk.Scrollbar(frame,orient="vertical",command=ed.yview);sx=ttk.Scrollbar(frame,orient="horizontal",command=ed.xview);ed.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        g.pack(side="left",fill="y");ed.pack(side="left",fill="both",expand=True);sy.pack(side="right",fill="y");sx.pack(side="bottom",fill="x")
        ed.insert("1.0",content);self.files.add(frame,text=name);self.files.select(frame)
        self.docs[str(frame)]={"frame":frame,"editor":ed,"path":None,"name":name,"modified":False,"gutter":g};self.editor=ed
        ed.bind("<<Modified>>",lambda e,x=ed:self._modified(x));ed.bind("<KeyRelease>",lambda e,x=ed:self._gutter(x));self._gutter(ed)
        return ed
    def _changed(self,event=None):
        try:self.editor=self.docs[str(self.nametowidget(self.files.select()))]["editor"]
        except Exception:self.editor=None
    def _modified(self,ed):
        if ed.edit_modified():
            for d in self.docs.values():
                if d["editor"] is ed:d["modified"]=True;self.files.tab(d["frame"],text=d["name"]+" *")
            ed.edit_modified(False)
    def _gutter(self,ed):
        for d in self.docs.values():
            if d["editor"] is ed:
                n=int(ed.index("end-1c").split(".")[0]);g=d["gutter"];g.configure(state="normal");g.delete("1.0","end");g.insert("1.0","\n".join(map(str,range(1,n+1))));g.configure(state="disabled");break
    def active(self):
        if not self.editor:self._changed()
        return self.editor
    def new_file(self):
        names=[d["name"] for d in self.docs.values()];i=1
        while f"Untitled-{i}" in names:i+=1
        self.new_tab(f"Untitled-{i}")
    def open_file(self):
        p=filedialog.askopenfilename(filetypes=[("Source files","*.easy *.cpp *.cc *.cxx"),("All files","*.*")])
        if p:self.open_path(p)
    def open_path(self,p):
        p=Path(p)
        for d in self.docs.values():
            if d["path"] and Path(d["path"])==p:self.files.select(d["frame"]);return
        ed=self.new_tab(p.name,p.read_text(encoding="utf-8",errors="replace"));d=self.docs[str(ed.master)];d["path"]=str(p);d["name"]=p.name;self.files.tab(d["frame"],text=p.name)
    def save_file(self):
        ed=self.active()
        if not ed:return
        d=self.docs[str(ed.master)]
        if not d["path"]:return self.save_as()
        Path(d["path"]).write_text(ed.get("1.0","end-1c"),encoding="utf-8");d["modified"]=False;self.files.tab(d["frame"],text=d["name"]);self.status.set("Saved "+d["path"])
    def save_as(self):
        ed=self.active()
        if not ed:return
        p=filedialog.asksaveasfilename(defaultextension=".easy",filetypes=[("EasyLang","*.easy"),("C++","*.cpp"),("All files","*.*")])
        if p:
            d=self.docs[str(ed.master)];d["path"]=p;d["name"]=Path(p).name;self.save_file()
    def close_tab(self):
        ed=self.active()
        if not ed:return
        d=self.docs[str(ed.master)]
        if d["modified"] and not messagebox.askyesno("Unsaved changes","Close without saving?"):return
        self.files.forget(d["frame"]);del self.docs[str(d["frame"])]
        if not self.docs:self.new_file()
        else:self._changed()
    def put(self,name,text):
        w=self.views[name];w.configure(state="normal");w.delete("1.0","end");w.insert("1.0",str(text));w.configure(state="disabled")
    def compile(self,run=False):
        ed=self.active()
        if not ed:return
        source=ed.get("1.0","end-1c");d=self.docs[str(ed.master)]
        for n in self.views:self.put(n,"")
        try:
            if self.language.get()=="C++17" or (d["path"] and Path(d["path"]).suffix.lower() in (".cpp",".cc",".cxx")):
                if not d["path"]:raise RuntimeError("Save the C++ source file before compiling.")
                self.put("Output",cpp_run(d["path"]));self.status.set("C++ build/run finished");self.results.select(4);return
            tokens=Lexer(source).scan();self.put("Tokens","TYPE\tLEXEME\tLINE\n"+"\n".join(map(str,tokens[:-1])))
            p=Parser(tokens).parse();self.put("AST",ast_text(p));sem=SemanticAnalyzer();sem.analyze(p)
            self.put("Symbol Table","NAME\tTYPE\tVALUE\tSCOPE\n"+"\n".join(f"{n}\t{x['type']}\t{x['value'] if x['value'] is not None else '<uninitialized>'}\tglobal" for n,x in sem.symbols.items()))
            self.put("Three Address Code",CodeGenerator().generate(p))
            if run:
                vm=Interpreter();out=vm.run(p);self.put("Output",out)
                for n,v in vm.values.items():sem.symbols[n]["value"]=v
                self.put("Symbol Table","NAME\tTYPE\tVALUE\tSCOPE\n"+"\n".join(f"{n}\t{x['type']}\t{x['value'] if x['value'] is not None else '<uninitialized>'}\tglobal" for n,x in sem.symbols.items()))
                self.status.set("Run completed successfully")
            else:self.status.set("Compilation successful")
        except Exception as e:self.put("Errors",str(e));self.status.set("Compilation failed");self.results.select(5)
    def debug(self):
        ed=self.active()
        if not ed:return
        try:p=Parser(Lexer(ed.get("1.0","end-1c")).scan()).parse();SemanticAnalyzer().analyze(p)
        except Exception as e:self.put("Errors",str(e));self.results.select(5);return
        win=tk.Toplevel(self);win.title("EasyLang Debugger");win.geometry("420x170");state={"pause":True,"step":True};self.debug_stop.clear()
        def hook(s,values):
            self.after(0,lambda:self.put("Debugger",f"Paused before line {s.line}\nVariables: {values}"))
            while state["pause"] and not self.debug_stop.is_set():time.sleep(.04)
            if state["step"]:state["pause"]=True
        def step():state.update(pause=False,step=True)
        def cont():state.update(pause=False,step=False)
        def pause():state["pause"]=True
        def reset():self.debug_stop.set();win.destroy()
        ttk.Label(win,text="Execution pauses before each statement.").pack(pady=10);row=ttk.Frame(win);row.pack()
        for label,fn in [("Step Over",step),("Continue",cont),("Pause",pause),("Reset",reset)]:ttk.Button(row,text=label,command=fn).pack(side="left",padx=4)
        def worker():
            try:r=Interpreter(hook,self.debug_stop).run(p);self.after(0,lambda:self.put("Output",r))
            except Exception as e:self.after(0,lambda:self.put("Errors",str(e)))
        threading.Thread(target=worker,daemon=True).start()
    def find(self):
        q=simpledialog.askstring("Find","Find text:")
        if q:
            e=self.active();e.tag_remove("find","1.0","end");p=e.search(q,"insert","end") or e.search(q,"1.0","end")
            if p:e.tag_add("find",p,f"{p}+{len(q)}c");e.tag_config("find",background="#536d9b")
    def replace(self):
        q=simpledialog.askstring("Replace","Find:")
        if q is None:return
        r=simpledialog.askstring("Replace","Replace with:")
        if r is not None:
            e=self.active();s=e.get("1.0","end-1c");e.delete("1.0","end");e.insert("1.0",s.replace(q,r))
    def auto_correct(self):
        e=self.active();ac=AutoCorrector(e.get("1.0","end-1c"));fix=ac.suggestions()
        if not fix:messagebox.showinfo("Auto Correction","No obvious safe corrections found.");return
        w=tk.Toplevel(self);w.title("Auto Correction");w.geometry("650x380");lb=tk.Listbox(w,selectmode="extended");lb.pack(fill="both",expand=True,padx=8,pady=8)
        for ln,desc,new in fix:lb.insert("end",f"Line {ln}: {desc} → {new.strip()}")
        def apply():
            selected=[fix[i][0] for i in (lb.curselection() or range(len(fix)))]
            e.delete("1.0","end");e.insert("1.0",ac.apply(selected));w.destroy()
        row=ttk.Frame(w);row.pack(pady=6)
        for label,fn in [("Apply Selected",apply),("Apply Safe Fixes",apply),("Undo",lambda:None),("Restore Original",lambda:(e.delete("1.0","end"),e.insert("1.0",ac.restore()))),("Close",w.destroy)]:ttk.Button(row,text=label,command=fn).pack(side="left",padx=3)
    def toggle_theme(self):
        self.dark=not self.dark;self._theme()
        for d in self.docs.values():d["editor"].configure(bg=self.panel,fg=self.fg,insertbackground=self.fg);d["gutter"].configure(bg=self.bg,fg=self.muted)
        for w in self.views.values():w.configure(bg=self.panel,fg=self.fg,insertbackground=self.fg)
        self.grammar.configure(bg=self.panel,fg=self.fg,insertbackground=self.fg);self.grammar_output.configure(bg=self.panel,fg=self.fg,insertbackground=self.fg)
    def _advanced_ui(self):
        left=ttk.Frame(self.advanced);left.pack(side="left",fill="y",padx=8,pady=8);ttk.Label(left,text="GRAMMAR RULES").pack(anchor="w")
        self.grammar=tk.Text(left,width=38,height=18,font=("Consolas",11),bg=self.panel,fg=self.fg);self.grammar.pack()
        self.grammar.insert("1.0","E -> E + T | T\nT -> T * F | F\nF -> ( E ) | id\n")
        ttk.Label(left,text="INPUT STRING").pack(anchor="w");self.ginput=tk.Entry(left);self.ginput.pack(fill="x");self.ginput.insert(0,"id + id * id")
        actions=[("FIRST/FOLLOW",self.first_follow),("LL(1) Table",self.ll1),("Predictive Parse",self.predict),("Remove Left Recursion",self.no_left_rec),("Left Factoring",self.factor),("Shift/Reduce",self.shift_reduce),("LR(0)/SLR(1)",self.slr)]
        for label,fn in actions:ttk.Button(left,text=label,command=fn).pack(fill="x",pady=2)
        right=ttk.Frame(self.advanced);right.pack(side="left",fill="both",expand=True,padx=8,pady=8)
        self.grammar_output=tk.Text(right,wrap="none",font=("Consolas",11),bg=self.panel,fg=self.fg);self.grammar_output.pack(fill="both",expand=True)
    def gaction(self,fn):
        try:g=Grammar.parse(self.grammar.get("1.0","end-1c"));out=fn(g)
        except Exception as e:out=str(e)
        self.grammar_output.delete("1.0","end");self.grammar_output.insert("1.0",out)
    def first_follow(self):
        def f(g):
            x=FirstFollow(g);return "FIRST / FOLLOW\n"+"\n".join(f"{n}: FIRST={{{', '.join(sorted(x.first[n]))}}} FOLLOW={{{', '.join(sorted(x.follow[n]))}}}" for n in g.rules)
        self.gaction(f)
    def ll1(self):
        def f(g):
            t=LL1Table(g);ts=sorted(g.terminals()|{END});out=["LL(1) TABLE","NT\t"+"\t".join(ts)]
            for n in g.rules:out.append(n+"\t"+"\t".join(" | ".join(" ".join(r) for r in t.cells[n].get(x,[])) for x in ts))
            out.extend(t.conflicts or ["No conflicts — grammar is LL(1)."]);return "\n".join(out)
        self.gaction(f)
    def predict(self):
        def f(g):
            ok,tr,msg=predictive_parse(LL1Table(g),self.ginput.get());return msg+"\n\nSTEP\tSTACK\tINPUT\tACTION\n"+"\n".join(f"{i+1}\t{a}\t{b}\t{c}" for i,(a,b,c) in enumerate(tr))
        self.gaction(f)
    def no_left_rec(self):self.gaction(lambda g:"Grammar after removing left recursion:\n"+remove_left_recursion(g).format())
    def factor(self):self.gaction(lambda g:"Grammar after left factoring:\n"+left_factor(g).format())
    def shift_reduce(self):
        def f(g):
            ok,tr,msg=shift_reduce_parse(g,self.ginput.get());return msg+"\n"+"\n".join(tr)
        self.gaction(f)
    def slr(self):self.gaction(slr_report)

def main():EasyLangStudio().mainloop()
if __name__=="__main__":main()
