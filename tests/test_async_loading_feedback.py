import unittest
from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


class AsyncLoadingFeedbackTest(unittest.TestCase):
    def test_interview_history_uses_accessible_skeleton_and_keeps_recovery_states(self):
        html = (STATIC / "entrevistas.html").read_text(encoding="utf-8")

        self.assertIn('id="history" aria-busy="true"', html)
        self.assertIn('id="list" class="list" role="region"', html)
        self.assertIn('class="skeleton skeleton-count" aria-hidden="true"', html)
        self.assertIn('role="status" aria-live="polite">Carregando entrevistas.', html)
        self.assertIn("@media(prefers-reduced-motion:reduce)", html)
        self.assertIn("Nenhuma entrevista registrada", html)
        self.assertIn('id="retryInterviews"', html)
        self.assertIn('role="alert"><strong>Não foi possível carregar as entrevistas agora.', html)

    def test_document_studio_lookup_has_accessible_loading_empty_and_retry_states(self):
        html = (STATIC / "document-studio.html").read_text(encoding="utf-8")

        self.assertIn('id="applicationPicker" aria-busy="true"', html)
        self.assertIn('id="applicationsLoading" role="status" aria-live="polite" aria-busy="true"', html)
        self.assertIn('id="applicationLookupLoading" role="status" aria-live="polite" aria-busy="true"', html)
        self.assertIn('id="retryApplications" type="button" hidden', html)
        self.assertIn('id="retryApplication" type="button" hidden', html)
        self.assertIn("Ainda não há candidaturas captadas.", html)
        self.assertIn("Você pode preencher manualmente ou tentar novamente.", html)
        self.assertIn("@media(prefers-reduced-motion:reduce)", html)
        self.assertIn("setApplicationLookupState({loading:true})", html)
        self.assertIn("setApplicationLookupState({message:error.message||'Não foi possível carregar esta vaga.',error:true,retry:true})", html)


if __name__ == "__main__":
    unittest.main()
