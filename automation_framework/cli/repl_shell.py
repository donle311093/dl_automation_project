from prompt_toolkit import PromptSession as _PromptSession

from cli.output import print_error, print_warning
from cli.session import SessionState


class ShellREPL:
    def __init__(self, session: SessionState, vm_name: str, vm):
        self.session = session
        self.vm_name = vm_name
        self.vm = vm
        self._prompt = _PromptSession()

    def run_loop(self):
        prompt_str = f"{self.session.platform}/vm[{self.vm_name}]/shell> "
        while True:
            try:
                line = self._prompt.prompt(prompt_str)
            except (EOFError, KeyboardInterrupt):
                break

            line = line.strip()
            if not line:
                continue
            if line in ("exit", "quit"):
                break

            try:
                result = self.vm.execute_command(line)
            except Exception as e:
                print_error(str(e))
                if self.session.debug:
                    import traceback
                    traceback.print_exc()
                continue

            stdout = result.get("stdout", "") or ""
            stderr = result.get("stderr", "") or ""
            exit_code = result.get("exit_code")

            if stdout:
                print(stdout, end="" if stdout.endswith("\n") else "\n")
            if stderr:
                print_warning(stderr.rstrip())
            if exit_code not in (None, 0):
                print_warning(f"[exit code: {exit_code}]")
