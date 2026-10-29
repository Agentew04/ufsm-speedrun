import type { Universe } from '../db/types'
import { num, pct } from '../lib/format'

export function Metodo({ universo }: { universo: Universe }) {
  return (
    <div className="metodo">
      <header>
        <span className="eyebrow">método</span>
        <h1>Como a conta é feita</h1>
        <p className="lede">
          Tudo roda no seu navegador sobre o SQLite do projeto. Sem servidor, sem request para a
          UFSM, sem telemetria. O banco é aberto em memória a partir do arquivo que você escolheu.
        </p>
      </header>

      <div className="metodo-grid">
        <div className="panel">
          <h3>1. Disciplina é global; oferta é local</h3>
          <p>
            A mesma disciplina (ex. <code>ELC1079</code>) aparece em vários currículos. Cursá-la
            uma vez conta em todos — é isso que gera o reaproveitamento. O app trabalha com o{' '}
            <code>disciplina_id</code>, nunca com a oferta, para não duplicar cadeiras.
          </p>

          <h3>2. Obrigatórias e cotas</h3>
          <p>
            Cada currículo tem obrigatórias (tipo 1) e núcleos com cota de horas (ex.: "DCG, 420 h").
            A cota é déficit: <code>ch_minima</code> menos a CH das obrigatórias daquele núcleo.
            O que sobra precisa ser preenchido por eletivas/DCG.
          </p>
          <p className="tiny dim">
            <b>DCG é escolha estratégica:</b> a cota com menu (128 das 129) não é hora livre — ela
            aceita só as disciplinas do menu, mas essas escolhas podem <b>dispensar obrigatórias de
            outro curso</b> quando são equivalentes (ex.: <code>ELC1070</code> como DCG do CC
            dispensa <code>UFSM01299</code> do SI). Cada escolha consome o orçamento de horas uma
            vez. A cota aberta aceita qualquer disciplina não-terminal. E{' '}
            <b>TCC/TCG, estágio e monografia nunca contam como DCG</b>.
          </p>
          <p className="tiny dim">
            Equivalências vêm de <code>v_equivalencia_efetiva</code>: oficial, julgada e{' '}
            <b>heurística</b> (palpite de ementa, marcado como “sugestão” na UI). O interruptor{' '}
            <em>DCG estratégica</em> liga/desliga as escolhas de DCG.
          </p>

          <h3>3. Custo de fechar um curso</h3>
          <p>
            <b>cadeiras novas</b> = obrigatórias do alvo que você ainda não tem.
            <br />
            <b>CH extra</b> = CH dessas cadeiras + cotas que o seu histórico não cobre.
            <br />
            <b>semestres extras</b> = bin-packing das cadeiras em semestres, respeitando
            pré-requisitos catalogados e a CH máxima por período do currículo-alvo.
          </p>
          <p className="note tiny">
            As horas das cotas de DCG/eletiva do seu curso entram como "já cumpridas" — por isso
            um curso com DCG de 420 h pode custar 0 h extras para quem já fechou a DCG do curso de
            origem. É a regra do projeto, não uma estimativa de quanto você estudou.
          </p>
        </div>

        <div className="panel">
          <h3>Premissas e limites</h3>
          <ul className="limits">
            <li>
              <b>Pré-requisitos oficiais são esparsos.</b> Usamos o que existe; onde não existe,
              ordenamos por <code>periodo_ideal</code>. O grafo não está completo e a UI avisa.
            </li>
            <li>
              <b>Equivalência oficial</b> aparece como aresta tracejada quando as duas disciplinas
              estão no mesmo currículo. A equivalência heurística por ementa (≥75%) ainda não entra
              no cálculo.
            </li>
            <li>
              <b>Cotas abertas</b> (núcleo com cota e nenhuma disciplina listada) viram "hora de
              eletiva a escolher" — 60 h por cadeira sintética.
            </li>
            <li>
              <b>Atividades complementares/extensão</b> não são disciplinas: aparecem à parte, nunca
              somadas aos semestres.
            </li>
            <li>
              <b>Campus</b> é um recorte prático: o ranking avisa quando o curso-alvo é de outro
              campus, mas não impede o cálculo.
            </li>
            <li>
              <b>CH total do currículo</b> nem sempre fecha com a soma das obrigatórias (a coleta já
              sinalizou isso). Por isso mostramos as duas coisas quando diferem.
            </li>
            <li>
              <b>Nada disso é grade oficial.</b> É uma estimativa explicável para comparar cursos.
            </li>
            <li>
              <b>Campus:</b> o filtro "só meu campus (+ EaD)" esconde cursos de outros campi
              (ranking/rede/run) e restringe as disciplinas de cota às ofertadas ali (proxy: campi
              dos currículos que listam a disciplina). O Mapa continua global.
            </li>
            <li>
              <b>ABI/núcleo comum</b> (ex.: "Artes Cênicas - Bacharelado", 960 h / 3 semestres) é a
              entrada, não o diploma — o curso continua na habilitação (Direção/Interpretação,
              2.756 h). Esses currículos ficam fora do ranking; aparecem só se você for aluno deles.
            </li>
            <li>
              <b>Núcleo flexível sem cota declarada</b> (ex.: Música/Bacharelado tem 1.110 h fora
              dos núcleos): a diferença contra <code>ch_total</code> entra como "horas do currículo
              fora dos núcleos mapeados", em vez de sumir da conta.
            </li>
          </ul>
        </div>
      </div>

      <div className="panel status-panel">
        <div className="panel-head">
          <span className="eyebrow">estado do banco</span>
          <h3>Quão completa está a coleta</h3>
        </div>
        <div className="status-grid">
          <div>
            <span className="kpi-label">cursos</span>
            <b>{num(universo.meta.cursos)}</b>
          </div>
          <div>
            <span className="kpi-label">versões selecionadas</span>
            <b>{num(universo.meta.versoes)}</b>
          </div>
          <div>
            <span className="kpi-label">ofertas</span>
            <b>{num(universo.meta.ofertas)}</b>
          </div>
          <div>
            <span className="kpi-label">disciplinas</span>
            <b>{num(universo.meta.disciplinas)}</b>
          </div>
          <div>
            <span className="kpi-label">pré-requisitos coletados</span>
            <b>{pct(universo.meta.coberturaPrereq)}</b>
          </div>
          <div>
            <span className="kpi-label">equivalências coletadas</span>
            <b>{pct(universo.meta.coberturaEquiv)}</b>
          </div>
        </div>
        <p className="note tiny">
          {universo.meta.comEmenta > 0 ? (
            <>
              {num(universo.meta.comEmenta)} de {num(universo.meta.disciplinas)} disciplinas com
              ementa ({pct(universo.meta.comEmenta / Math.max(1, universo.meta.disciplinas))}) — a
              fase 6a ainda não usa similaridade de ementa; só a equivalência oficial/julgada.
            </>
          ) : (
            <>
              Núcleo enxuto: as ementas ficam em <code>ementas.db</code> (e a bibliografia em{' '}
              <code>bibliografias.db</code>), carregadas sob demanda. O otimizador não depende
              delas.
            </>
          )}
        </p>
        {(universo.meta.coberturaPrereq < 0.99 || universo.meta.coberturaEquiv < 0.99) && (
          <p className="note tiny">
            A coleta de pré-requisitos/equivalências ainda está rodando. Reexporte o banco quando
            ela terminar: o cálculo fica mais preciso sem mexer no front.
          </p>
        )}
      </div>

      <div className="panel">
        <h3>Atualizar os dados</h3>
        <pre className="code">
{`# 1. copia o banco com o WAL aplicado (não copie o .db na mão)
python web/scripts/snapshot-db.py

# 2. modo dev
cd web && npm install && npm run dev

# 3. build estático (dist/ roda em qualquer host, inclusive offline)
npm run build`}
        </pre>
        <p className="tiny dim">
          O arquivo <code>public/ufsm.db</code> é lido automaticamente ao abrir a página. Sem ele, a
          tela inicial pede o arquivo (arrastar e soltar também funciona). Nada é enviado pela rede.
        </p>
      </div>
    </div>
  )
}
