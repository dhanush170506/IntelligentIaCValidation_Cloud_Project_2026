"""Optional smoke checks. They never install or require external tools."""
import shutil
def main():
 available=[name for name in ("terraform","checkov","cfn-lint","tflint") if shutil.which(name)]
 if not available: print("MODULE 3 REAL-TOOL SMOKE: SKIPPED (tools unavailable)"); return
 # Detailed adapter behavior remains covered by mocked tests; availability is
 # deliberately reported without running a mutating Terraform command.
 print("MODULE 3 REAL-TOOL SMOKE: AVAILABLE " + ", ".join(available))
if __name__ == "__main__": main()
