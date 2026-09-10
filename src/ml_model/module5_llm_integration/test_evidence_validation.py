from .evidence_validation import EvidenceConsistencyValidator
def main():
 uir={"resources":[{"id":"aws_instance.web"}]}; evidence=({"evidence_id":"telemetry:ok","value":95},)
 v=EvidenceConsistencyValidator()
 assert v.validate(text="aws_instance.web telemetry:ok",uir=uir,evidence=evidence,agent_results=()).accepted
 for text in ("aws_instance.other", "telemetry:invented", "Cost is $999", "destroy aws_instance.web", None): assert not v.validate(text=text,uir=uir,evidence=evidence,agent_results=()).accepted
 assert v.validate(text=None,uir=uir,evidence=evidence,agent_results=()).fallback_text == v.validate(text=None,uir=uir,evidence=evidence,agent_results=()).fallback_text
 print("MODULE 5 EVIDENCE VALIDATION TESTS: PASSED")
if __name__ == "__main__": main()
