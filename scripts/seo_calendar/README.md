# Calendário SEO: coleta e entrega (MDL-03)

A automação consulta somente o Search Console, monta quatro pautas para as
próximas quatro semanas e grava um CSV local. Ela não altera páginas do site.
O e-mail é uma proposta para revisão do owner e aguarda aceite antes de
qualquer publicação.

## Preparar e revisar

Instale `scripts/seo_calendar/requirements.txt` no ambiente da execução. O
cofre deve injetar `MDL_GSC_CREDENTIAL_FILE` como referência ao arquivo de
credencial de leitura do Search Console.

Na raiz do repositório, rode:

```powershell
$env:PYTHONPATH = "scripts"
python -m seo_calendar.run
```

A execução padrão é dry-run: coleta os dados reais, exige dados suficientes,
gera `scripts/seo_calendar/artifacts/calendario-seo.csv` e exibe propriedade,
período, quatro pautas e digest. Ela não conecta ao SMTP. Revise o CSV antes de
solicitar envio.

## Entrega ao cofre

Para envio, o cofre injeta exclusivamente estas variáveis de ambiente:

| Variável | Conteúdo injetado |
| --- | --- |
| `MDL_SMTP_HOST` | Host SMTP |
| `MDL_SMTP_PORT` | Porta SMTP com STARTTLS |
| `MDL_SMTP_USER` | Usuário SMTP |
| `MDL_SMTP_PASSWORD` | Senha SMTP |
| `MDL_SMTP_FROM` | Remetente autorizado |
| `MDL_SMTP_RECIPIENTS` | Destinatários do cofre, separados por vírgula ou ponto e vírgula |
| `MDL_DELIVERY_AUDIT_FILE` | Caminho opcional para o registro operacional local |

O envio exige `--send`, confirmação do digest da execução e a branch
`darkfac/m1-seo`. `master` e qualquer outra branch são recusadas. O exemplo
abaixo usa o digest mostrado pela execução de revisão:

```powershell
python -m seo_calendar.run --send --confirm-digest <SHA256_DA_REVISAO>
```

O e-mail contém propriedade, período, as quatro pautas com consultas e métricas,
e o CSV como anexo. STARTTLS é obrigatório. Se o SMTP recusar qualquer
destinatário, a execução falha. Após aceitação de todos, a ferramenta registra
somente timestamp UTC, digest e Message-ID em
`scripts/seo_calendar/artifacts/deliveries.jsonl` (ignorado pelo Git). Não
registra destinatários, host, usuário ou senha.

Não execute `git add` nos artefatos gerados. A implantação do site não faz
parte desta automação.
