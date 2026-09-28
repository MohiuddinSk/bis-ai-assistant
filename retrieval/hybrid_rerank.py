"""Deterministic category-aware reranking shared by Chroma retrieval callers."""
import re
GENERIC={'bis','product','certification','standard','application','document','requirements','scheme'}
CONCEPTS={
 'fees':('fee','fees','charge','charges','payment','फी','शुल्क','फीस','शुल्क','கட்டண','ফি'),
 'laboratories':('laboratory','lab','testing','scope','validity','प्रयोगशाला','चाचणी','ஆய்வக','পরীক্ষাগার'),
 'fmcs':('fmcs','form v','foreign manufacturer','फॉर्म','फॉर्म','படிவ','ফর্ম'),
 'helmet':('helmet','is 4151','हेलमेट','शिरस्त्राण','ஹெல்மெட்','হেলমেট'),
 'jewellery':('jeweller','jewelry','jewellery','hallmark','जौहरी','दागिने','நகை','গয়না'),
 'toys':('toy','toys','battery','electric toy','is 9873','खिलौ','खेळण','பொம்மை','খেলনা')}
def intents(query):
 q=query.lower(); return [name for name,terms in CONCEPTS.items() if any(term in q for term in terms)]
def tokens(text): return {x for x in re.findall(r'[a-z0-9]+',text.lower()) if len(x)>2 and x not in GENERIC}
def rerank(query, rows):
 cats=set(intents(query)); qtokens=tokens(query); out=[]
 for order,row in enumerate(rows):
  m=row['metadata']; text=row['document']; category=m.get('category','v3_toys'); category_boost=.35 if category in cats else 0
  lexical=.02*len(qtokens & tokens(text)); ident=.5 if re.search(r'\bis\s*4151\b',query,re.I) and '4151' in text else 0
  score=(1-float(row['distance']))+category_boost+lexical+ident
  out.append((score,order,row))
 return [r for _,_,r in sorted(out,key=lambda x:(-x[0],x[1],x[2]['id']))]
