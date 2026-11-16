"""Decode restart journal elements with the standard JSON decoder.

Only the envelope/account/event containers are traversed incrementally. Each
event and ordinary field still uses JSONDecoder.raw_decode, retaining its number,
escaping and duplicate-key semantics without a whole-history text allocation.
"""
import json


class Reader:
    def __init__(self,chunks):
        self.chunks=iter(chunks);self.text='';self.pos=0;self.eof=False
        self.decoder=json.JSONDecoder()

    def fill(self,minimum=0):
        if self.pos:
            self.text=self.text[self.pos:];self.pos=0
        parts=[self.text];size=len(self.text);goal=max(minimum,size+1)
        while size<goal and not self.eof:
            try:
                part=next(self.chunks);parts.append(part);size+=len(part)
            except StopIteration:self.eof=True
        self.text=''.join(parts)

    def peek(self):
        while True:
            while self.pos<len(self.text) and self.text[self.pos] in ' \t\r\n':self.pos+=1
            if self.pos<len(self.text):return self.text[self.pos]
            if self.eof:return ''
            self.fill()

    def take(self,expected):
        if self.peek()!=expected:raise ValueError('Invalid restart JSON punctuation')
        self.pos+=1

    def raw(self,*,key=False):
        self.peek()
        while True:
            try:value,end=self.decoder.raw_decode(self.text,self.pos)
            except ValueError:
                if self.eof:raise
                self.fill(max(65536,2*(len(self.text)-self.pos)));continue
            # A scalar ending at a chunk boundary may continue in the next
            # chunk (1 -> 1e+20). Never accept a numeric prefix prematurely.
            allowed=' \t\r\n,]}' + (':' if key else '')
            if end<len(self.text) and self.text[end] in allowed:
                self.pos=end;return value
            if self.eof:
                self.pos=end;return value
            self.fill()

    def value(self,mode):
        char=self.peek()
        if char=='{' and mode in {'root','accounts','account'}:
            return self.mapping(mode)
        if char=='[' and mode=='events':return self.events()
        return self.raw()

    def mapping(self,mode):
        self.take('{');result={}
        if self.peek()=='}':self.pos+=1;return result
        while True:
            if self.peek()!='"':raise ValueError('Restart JSON object key required')
            key=self.raw(key=True)
            self.take(':')
            child=('accounts' if mode=='root' and key=='accounts' else
                   'account' if mode=='accounts' else
                   'events' if mode in {'root','account'} and key=='events' else None)
            result[key]=self.value(child)
            char=self.peek()
            if char=='}':self.pos+=1;return result
            self.take(',')

    def events(self):
        self.take('[');result=[]
        if self.peek()==']':self.pos+=1;return result
        while True:
            result.append(self.raw())
            char=self.peek()
            if char==']':self.pos+=1;return result
            self.take(',')


def load(chunks):
    reader=Reader(chunks)
    result=reader.value('root')
    # Exhaust the decompressor/checksum generator before exposing any data.
    if reader.peek():raise ValueError('Trailing restart JSON data')
    return result
