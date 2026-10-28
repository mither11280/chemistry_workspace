"""Candidate generation ONLY. No candidate produced here is approved for the bank.
An explicit source-bound decision, authored after inspecting task/scoring evidence,
is required by rebuild_teaching_bank.py. Scores are never represented as accuracy.
"""
import re

# Chapter, task/evidence hints. These deliberately recall broadly: background and
# distractor matches are corrected or rejected at the separate decision stage.
RULES=[
(1,r'isotop|relative atomic mass|nucleon|proton|neutron|electron configuration|electronic configuration|ionisation|ionization|atomic radius|ionic radi|isoelectronic|orbital|first ion|ionization|successive ion','原子粒子、电子结构或电离能'),
(2,r'empirical formula|molecular formula|percentage by mass|% by mass|mole|stoichiometr|concentration|titration|titrate|volume of.*gas|mass of.*formed|yield|limiting reagent|avogadro|react.*completely|complete combustion','化学计量、组成或溶液计算'),
(3,r'bonding|bond angle|shape|lone pair|dot.and.cross|sigma|pi bond|π bond|hybridis|hybridiz|hydrogen bond|electronegativity|intermolecular|giant covalent|giant ionic|van der waals|delocalis|delocaliz|polar molecule','成键、结构及分子间作用力'),
(4,r'ideal gas|pV|PV|gas constant|liquid.*vapour|kinetic.*gas|deviat.*ideal|behav.*ideal|boiling.*pressure','物态与理想气体模型'),
(5,r'enthalpy|hess|exotherm|endotherm|bond energ|calorimet|heat change|heat capacity|heat.*reaction','热化学'),
(6,r'oxidation number|oxidation state|oxidising agent|oxidizing agent|reducing agent|disproportion|redox|electron.*transfer|oxidised and reduced','氧化还原与电子守恒'),
(7,r'equilibri|le chatelier|\bKc\b|\bKp\b|partial pressure|strong acid|weak acid|Br.nsted|brønsted|proton donor|proton acceptor','平衡或酸碱理论'),
(8,r'rate of|reaction rate|activation energy|boltzmann|collision|catalyst|catalys|catalyz|speed of|rate.*reaction','反应速率与催化'),
(9,r'period 3|third period|periodicity|across.*period|chlorides of|oxides of','第三周期性质'),
(10,r'group (?:2|II)|magnesium|calcium|strontium|barium|radium|thermal stability|thermal decomposition','第2族性质或反应'),
(11,r'group (?:17|VII)|halogen|chlorine|bromine|iodine|chlorate|hypochlor|sodium iodide|sodium bromide','卤素性质或反应'),
(12,r'nitrogen|sulfur|sulphur|ammonia|ammonium|nitrate|nitrite|nitric|sulfuric|sulphuric|catalytic converter|acid rain|silver nitrate|AgNO3|limewater|BaCl2','氮硫或无机鉴定'),
(13,r'isomer|chiral|stereoisom|functional group|homologous|systematic name|nomenclature|skeletal formula|structural formula','有机结构、命名与异构'),
(14,r'alkene|alkane|hydrocarbon|propene|ethene|methane|polymer|monomer|repeat unit|cracking|electrophilic addition|free.radical','烃、加成与聚合'),
(15,r'halogeno|haloalkane|halogenoalkane|bromoethane|chloroethane|nucleophilic substitution|\bSN[12]\b|C.Br|C.Cl|KCN in ethanol','卤代物反应或机理'),
(16,r'alcohol|ethanol|propan.ol|hydroxy|hydroxyl|dehydrat','羟基化合物'),
(17,r'carbox|ester|nitrile|hydrolys.*cyan|C[≡#]N|\bCOOH\b|ethanoic|acyl','羧酸、酯或腈'),
(18,r'aldehyde|ketone|carbonyl|NaBH4|Tollens|Fehling|DNPH|dinitrophenyl|iodoform|alkaline I2|functional group.*test|chemical test','羰基或有机官能团检验'),
(19,r'infra.?red|wavenumber|fragment|M\s*\+\s*1|\[M.1\]|13C.*abundance','红外或有机质谱')]

def compact(text):return re.sub(r'\s+',' ',text).strip()
def propose(record):
    text='\n'.join([record['task'],record.get('context',''),record.get('answer','')]);hits=[]
    for n,pattern,reason in RULES:
        if re.search(pattern,text,re.I):hits.append({'chapter':n,'reason':reason})
    return hits

def task_stem(text):
    parts=re.split(r'(?m)^\s*A\s+',text,maxsplit=1)
    return parts[0] if parts else text
