"""Candidate topic rules, not validated syllabus-statement mapping."""
import math,re
RULES=[('atomic', '原子结构', 'Atomic structure', 'ionisation|electron configuration|orbital|isotope|proton|neutron'), ('stoich', '物质的量', 'Atoms, molecules and stoichiometry', '\\bmoles?\\b|mol dm|mass of|empirical|molecular formula|avogadro'), ('bonding', '化学键', 'Chemical bonding', 'bond angle|bonding|hydrogen bond|electronegativity|intermolecular|shape of|giant covalent|sigma|covalent bond'), ('states', '物质状态', 'States of matter', 'ideal gas|pressure|vapour|vapor|lattice'), ('energetics', '化学能量', 'Chemical energetics', 'enthalpy|hess|exothermic|endothermic|bond energ'), ('electro', '氧化还原', 'Electrochemistry', 'oxidation number|oxidising|reducing agent|redox'), ('equilibrium', '化学平衡', 'Equilibria', 'equilibrium|equilibria|le chatelier|Kc|Kp'), ('kinetics', '反应速率', 'Reaction kinetics', 'activation energy|boltzmann|rate of|catalyst|catalys'), ('periodic', '周期表与无机', 'Periodicity and inorganic chemistry', 'period 3|group 2|group 17|halogen|chlorine|bromine|nitrate|sulfur|sulphur|ammonia'), ('organic', '有机化学', 'Organic chemistry', 'alkane|alkene|alcohol|aldehyde|ketone|ester|carboxylic|polymer|organic|isomer|hydrocarbon|halogeno|ethanol'), ('analysis', '分析技术', 'Analytical techniques', 'infra.red|infrared|mass spectrum|mass spectrom|spectra')]

def classify(text):
    results=[]
    for ident,_,_,pattern in RULES:
        hits=len(re.findall(pattern,text,re.I))
        if hits:results.append({'topic_id':ident,'evidence_count':hits,'confidence':round(min(.9,.45+.12*math.log2(1+hits)),3)})
    return [r['topic_id'] for r in results] or ['unclassified'],{'method':'keyword-rules-v2','confidence_semantics':'heuristic support score, not measured accuracy or probability','suggestions':results,'syllabus_mapping':'unverified'}
