"""Candidate element-to-PDF passage linkage; never certification."""
from io import BytesIO
import re
from pypdf import PdfReader

_CHARS=r"[A-Za-z0-9_$]"
_GUID=re.compile(rf"(?<!{_CHARS}){_CHARS}{{22}}(?!{_CHARS})")

def link_pdf_evidence(pdf_bytes, elements, max_per_element=3):
    """Link exact GlobalIds; keep class-level mentions separately as unverified candidates."""
    model_ids={str(e.get("GlobalId")):e for e in elements if e.get("GlobalId")}
    classes={str(e.get("Type") or "") for e in elements}
    reader=PdfReader(BytesIO(pdf_bytes))
    out=[]; seen=set()
    for page_no,page in enumerate(reader.pages,1):
        lines=[re.sub(r"\s+"," ",x).strip() for x in (page.extract_text() or "").splitlines() if x.strip()]
        for i,line in enumerate(lines):
            if len(line)<3:continue
            # Only the line containing the identifier owns the next line's requirement.
            snippet=(line+(" "+lines[i+1] if _GUID.search(line) and i+1<len(lines) else ""))[:950]
            found=set(_GUID.findall(snippet)) & model_ids.keys()
            for gid in sorted(found):
                key=(page_no,gid)
                if key in seen:continue
                seen.add(key)
                e=model_ids[gid]
                out.append({"GlobalId":gid,"IFCType":e.get("Type",""),"ElementName":e.get("Name",""),
                    "PDFPage":page_no,"EvidenceLevel":"EXACT_GLOBALID_CANDIDATE",
                    "CandidateText":snippet,"Applicability":"UNVERIFIED","ComplianceVerdict":"NOT_ASSESSABLE"})
            if not found:
                for typ in sorted(classes):
                    if not typ or not re.search(r"(?<![A-Za-z0-9])"+re.escape(typ)+r"(?![A-Za-z0-9])",line,re.I):continue
                    key=(page_no,typ)
                    if key in seen:continue
                    seen.add(key)
                    out.append({"GlobalId":"","IFCType":typ,"ElementName":"","PDFPage":page_no,
                        "EvidenceLevel":"IFC_CLASS_CANDIDATE","CandidateText":snippet,
                        "Applicability":"UNVERIFIED","ComplianceVerdict":"NOT_ASSESSABLE"})
    counts={}; bounded=[]
    for link in out:
        key=link["GlobalId"] or "CLASS:"+link["IFCType"]
        counts[key]=counts.get(key,0)+1
        if counts[key]<=max_per_element:bounded.append(link)
    return bounded
