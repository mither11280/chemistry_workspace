"""Exam period and current-topic suggestions are distinct from content compatibility."""

CURRENT='cie-9701-2025-2027'
TOPIC_SECTIONS={'atomic':['1'],'stoich':['2'],'bonding':['3'],'states':['4'],'energetics':['5'],'electro':['6'],'equilibrium':['7'],'kinetics':['8'],'periodic':['9','10','11','12'],'organic':[str(x) for x in range(13,22)],'analysis':['22'],'unclassified':[]}
PERIODS={2018:('2016-2018','https://www.cambridgeinternational.org/Images/164502-2016-2018-syllabus.pdf','archive-reference-not-retrieved'),2019:('2019-2021','https://www.cambridgeinternational.org/Images/329530-2019-2021-syllabus.pdf','archive-reference-not-retrieved'),2020:('2019-2021','https://www.cambridgeinternational.org/Images/329530-2019-2021-syllabus.pdf','archive-reference-not-retrieved'),2021:('2019-2021','https://www.cambridgeinternational.org/Images/329530-2019-2021-syllabus.pdf','archive-reference-not-retrieved')}

def metadata(year,topics,session):
    if year<=2021:period,url,status=PERIODS.get(year,('unknown',None,'unknown'))
    elif year<=2024:period,url,status='2022-2024','https://www.cambridgeinternational.org/Images/554616-2022-2024-syllabus.pdf','official-cover-period-verified'
    else:period,url,status='2025-2027','https://www.cambridgeinternational.org/Images/664563-2025-2027-syllabus.pdf','official-local-document-period-verified'
    return {'original_syllabus':{'syllabus_id':'cie-9701-'+period,'period':period,'document_revision':None,'period_basis':'exam-year-range','verification':status,'reference':url},'current_syllabus':{'syllabus_id':CURRENT,'compatibility':'same-period' if period=='2025-2027' else 'unknown','reason':'Same examination syllabus period; topic labels remain suggestions.' if period=='2025-2027' else 'No question-level mapping of removed, changed or retained statements has been verified.','topic_mapping':[{'topic_id':t,'current_sections':TOPIC_SECTIONS.get(t,[]),'status':'candidate-heading-map-not-statement-validation','method':'curated-broad-topic-crosswalk-v1'} for t in topics]},'exam_series_status':'cancelled-published-practice-materials' if year==2020 and session=='May/June' else 'historical-or-completed'}


def enrich(index):
    for q in index['questions']:q['metadata'].update(metadata(q['year'],q['topics'],q['session']))
    return index
