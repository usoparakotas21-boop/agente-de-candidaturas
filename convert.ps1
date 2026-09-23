$word = New-Object -ComObject Word.Application
$doc = $word.Documents.Open("C:\agente_curriculos\livro_disc\DISC_Hackeado.docx")
$doc.SaveAs([ref]"C:\agente_curriculos\output\pdf\DISC_Hackeado.pdf", [ref]17)
$doc.Close()
$doc2 = $word.Documents.Open("C:\agente_curriculos\output\docx\DISC_Hackeado_Edicao_Completa.docx")
$doc2.SaveAs([ref]"C:\agente_curriculos\output\pdf\DISC_Hackeado_Edicao_Completa.pdf", [ref]17)
$doc2.Close()
$word.Quit()
