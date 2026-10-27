"""Build an auditable starter bank. Candidate crops are never marked reviewed."""
import fitz, re, json, hashlib, shutil, argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parents[1]/'03_真题/9701'
TOPICS=[('atomic','原子结构','Atomic structure',r'ionisation|electron configuration|orbital|isotope|proton|neutron'),('stoich','物质的量','Atoms, molecules and stoichiometry',r'\bmoles?\b|mol dm|mass of|empirical|molecular formula|avogadro'),('bonding','化学键','Chemical bonding',r'bond angle|bonding|hydrogen bond|electronegativity|intermolecular|shape of|giant covalent|sigma|covalent bond'),('states','物质状态','States of matter',r'ideal gas|pressure|vapour|vapor|lattice'),('energetics','化学能量','Chemical energetics',r'enthalpy|hess|exothermic|endothermic|bond energ'),('electro','氧化还原','Electrochemistry',r'oxidation number|oxidising|reducing agent|redox'),('equilibrium','化学平衡','Equilibria',r'equilibrium|equilibria|le chatelier|Kc|Kp'),('kinetics','反应速率','Reaction kinetics',r'activation energy|boltzmann|rate of|catalyst|catalys'),('periodic','周期表与无机','Periodicity and inorganic chemistry',r'period 3|group 2|group 17|halogen|chlorine|bromine|nitrate|sulfur|sulphur|ammonia'),('organic','有机化学','Organic chemistry',r'alkane|alkene|alcohol|aldehyde|ketone|ester|carboxylic|polymer|organic|isomer|hydrocarbon|halogeno|ethanol'),('analysis','分析技术','Analytical techniques',r'infra.red|infrared|mass spectrum|mass spectrom|spectra')]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def region(page,box):return {'page':page+1,'bbox':[round(v,2) for v in box]}
def qp_regions(doc,paper):
 starts=[];expected=1
 for pi,p in enumerate(doc):
  if pi==0:continue
  for w in sorted(p.get_text('words'),key=lambda w:(w[1],w[0])):
   if 45<=w[0]<=56 and 55<w[1]<760 and w[4]==str(expected):
    starts.append((expected,pi,w[1]-4));expected+=1
 result={}
 for j,(n,pi,y) in enumerate(starts):
  end=starts[j+1][1:] if j+1<len(starts) else (len(doc)-1,780)
  regions=[]
  for k in range(pi,end[0]+1):
   p=doc[k];txt=p.get_text()
   if k>pi and ('BLANK PAGE' in txt or 'The Periodic Table' in txt or 'The Periodic Table of Elements' in txt):break
   top=y if k==pi else 56;bottom=end[1]-5 if k==end[0] and j+1<len(starts) else min(780,p.rect.height-56)
   # Keep question text above constants even when both share a page.
   for heading in ['Important values', 'Important Values']:
    hits=p.search_for(heading)
    if hits:bottom=min(bottom,hits[0].y0-8)
   totals=p.search_for('[Total:')
   if paper==2 and totals:bottom=min(bottom,totals[-1].y1+8)
   # Stop after the final question total, before appended data pages.
   if bottom>top+8:regions.append(region(k,[44,top,552,bottom]))
   if paper==2 and re.search(r'\[Total\s*:\s*\d+\]',txt):break
  result[n]=regions
 return result

def ms_regions(doc,paper):
 result={};answers={}
 if paper==1:
  for pi,p in enumerate(doc):
   words=p.get_text('words')
   for w in words:
    if not(w[4].isdigit() and 70<float(w[0])<160 and 60<w[1]<760):continue
    n=int(w[4]);row=[z for z in words if abs(z[1]-w[1])<3]
    ans=next((z[4] for z in row if z[4] in ['A','B','C','D']),None)
    if ans and 1<=n<=40:
     result[n]=[region(pi,[49,w[1]-5,p.rect.width-49,w[3]+5])];answers[n]=ans
 else:
  for pi,p in enumerate(doc):
   rows=[]
   for w in p.get_text('words'):
    m=re.match(r'^(\d+)\([a-z]\)',w[4])
    if m and w[0]<140:rows.append((int(m[1]),w[1]))
   if not rows:continue
   groups=[]
   for n,y in sorted(set(rows),key=lambda r:r[1]):
    if not groups or groups[-1][0]!=n:groups.append((n,y))
   for j,(n,y) in enumerate(groups):
    # The next question's repeated table header lies above its first row.
    bottom=groups[j+1][1]-25 if j+1<len(groups) else p.rect.height-55
    result.setdefault(n,[]).append(region(pi,[60,max(60,y-7),p.rect.width-60,bottom]))
 return result,answers

def main():
 parser=argparse.ArgumentParser(description='Import the 2024-2026 March CIE 9701 Paper 12/22 starter bank from local PDFs.')
 parser.add_argument('--source-root',type=Path,default=SOURCE,help='Directory containing 2024_M, 2025_M, 2026_M PDF folders')
 parser.add_argument('--syllabus',type=Path,default=ROOT.parents[1]/'04_课程与教研/01_考试局/CIE_剑桥/AS_A_Level_Chemistry_9701/考纲/664563-2025-2027-syllabus_wrapper.pdf',help='Local 9701 2025-2027 syllabus PDF')
 args=parser.parse_args()
 source_root=args.source_root.expanduser().resolve()
 for folder in ['data/sources','data/cache']:(ROOT/folder).mkdir(parents=True,exist_ok=True)
 questions=[];sources={};report=[]
 syllabus=args.syllabus.expanduser().resolve()
 syllabus_dst=ROOT/'data/sources/9701-syllabus-2025-2027.pdf'
 shutil.copy2(syllabus,syllabus_dst)
 sources[syllabus_dst.name]={'sha256':sha(syllabus_dst),'original_path':str(syllabus),'pages':len(fitz.open(syllabus_dst)),'identity_evidence':'Cambridge 9701 syllabus 2025-2027, version 1; topic candidates not yet mapped to statements'}
 for year in [2024,2025,2026]:
  for paper in [1,2]:
   code=f'{paper}2';stem=f'9701_m{year%100}_';paths={}
   for kind in ['qp','ms']:
    src=source_root/f'{year}_M'/f'{stem}{kind}_{code}.pdf'
    dst=ROOT/'data/sources'/src.name;shutil.copy2(src,dst);paths[kind]=dst
   qdoc=fitz.open(paths['qp']);mdoc=fitz.open(paths['ms'])
   for kind,doc in [('qp',qdoc),('ms',mdoc)]:
    cover=doc[0].get_text();assert f'9701/{code}' in cover and str(year) in cover,(paths[kind],'identity mismatch')
    sources[paths[kind].name]={'sha256':sha(paths[kind]),'original_path':str(source_root/f'{year}_M'/paths[kind].name),'pages':len(doc),'identity_evidence':cover[:1600]}
   qrs=qp_regions(qdoc,paper);mrs,answers=ms_regions(mdoc,paper)
   if paper==1:assert len(qrs)==40 and len(answers)==40,(year,len(qrs),len(answers))
   for n,rs in qrs.items():
    text='\n'.join(qdoc[r['page']-1].get_text(clip=fitz.Rect(r['bbox'])) for r in rs)
    totals=re.findall(r'\[Total\s*:\s*(\d+)\]',text)
    marks=1 if paper==1 else int(totals[-1]) if totals else None
    # One final short structured question can omit a printed grand total.
    if paper==2 and marks is None:
     values=re.findall(r'\[(\d+)\]',text);marks=sum(map(int,values)) if values else None
    tags=[t[0] for t in TOPICS if re.search(t[3],text,re.I)]
    clean=' '.join(text.split());clean=re.sub(r'^\d+\s*','',clean)
    ident=f'cie-9701-m{year%100}-{code}-q{n}'
    assert n in mrs,('missing answer',ident)
    questions.append({'id':ident,'year':year,'session':'February/March','paper':paper,'variant':code,'number':n,'marks':marks,'topics':tags or ['unclassified'],'text':clean,'summary':clean[:230],'qp':paths['qp'].name,'ms':paths['ms'].name,'question_regions':rs,'answer_regions':mrs[n],'answer':answers.get(n),'review_status':'pending_review','classification_basis':'Keyword candidate; not verified against individual syllabus statements','granularity':'question' if paper==1 else 'whole_question'})
   report.append({'year':year,'paper':paper,'questions':len(qrs),'marks':sum(q['marks'] or 0 for q in questions if q['year']==year and q['paper']==paper)})
 bank={'schema_version':1,'bank_id':'cie-9701-as-starter','revision':'2026-10-27.1','topics':[{'id':t[0],'name':t[1],'english':t[2]} for t in TOPICS]+[{'id':'unclassified','name':'待分类','english':'Unclassified'}],'sources':sources,'questions':questions,'coverage':report,'review_note':'自动切分候选，尚未独立逐题复核。Paper 2 保留整道大题。'}
 (ROOT/'data/bank.json').write_text(json.dumps(bank,ensure_ascii=False,indent=2))
 print(json.dumps(report,ensure_ascii=False));print(len(questions),'questions')
if __name__=='__main__':main()
