package com.itau.sg2.custodiaposvenda.arquitetura;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Trava a regra de dependência descrita no ADR-0003.
 * <p>
 * Feito com varredura de imports em vez de ArchUnit de propósito: são ~40 linhas, sem dependência
 * nova, e roda em qualquer lugar. ArchUnit expressaria mais (ciclos, camadas, convenções de nome)
 * e é a evolução natural — mas a regra que realmente importa é esta, e ela não pode depender de
 * uma biblioteca estar disponível para ser verificada.
 */
class RegraDeDependenciaTest {

    private static final Path RAIZ = Path.of("src/main/java/com/itau/sg2/custodiaposvenda");

    @Test
    @DisplayName("domain não depende de application nem de infrastructure")
    void dominioNaoDependeDeNinguem() throws IOException {
        List<String> violacoes = violacoes(
                RAIZ.resolve("domain"),
                "import com.itau.sg2.custodiaposvenda.application",
                "import com.itau.sg2.custodiaposvenda.infrastructure");

        assertTrue(violacoes.isEmpty(),
                "domain deve ser puro. Violações:\n" + String.join("\n", violacoes));
    }

    @Test
    @DisplayName("application não depende de infrastructure")
    void aplicacaoNaoDependeDeInfraestrutura() throws IOException {
        List<String> violacoes = violacoes(
                RAIZ.resolve("application"),
                "import com.itau.sg2.custodiaposvenda.infrastructure");

        assertTrue(violacoes.isEmpty(),
                "application só pode conhecer portas. Quando precisar de algo de infrastructure, "
                        + "declare uma porta em application/ports/outbound. Violações:\n"
                        + String.join("\n", violacoes));
    }

    /**
     * O domínio não pode conhecer framework. A exceção é {@code jackson-annotations}: a tolerância
     * a enum desconhecido precisa estar no próprio enum porque a desserialização acontece antes do
     * listener (ADR-0001). É anotação, não acoplamento comportamental.
     */
    @Test
    @DisplayName("domain não importa framework, exceto jackson-annotations")
    void dominioNaoImportaFramework() throws IOException {
        List<String> violacoes = violacoes(
                RAIZ.resolve("domain"),
                "import org.springframework",
                "import tools.jackson",
                "import io.micrometer",
                "import org.slf4j",
                "import software.amazon");

        assertTrue(violacoes.isEmpty(),
                "domain deve ser tecnologicamente neutro. Violações:\n" + String.join("\n", violacoes));
    }

    private List<String> violacoes(Path pacote, String... proibidos) throws IOException {
        List<String> encontradas = new ArrayList<>();

        try (Stream<Path> arquivos = Files.walk(pacote)) {
            for (Path arquivo : arquivos.filter(p -> p.toString().endsWith(".java")).toList()) {
                List<String> linhas = Files.readAllLines(arquivo);
                for (int i = 0; i < linhas.size(); i++) {
                    String linha = linhas.get(i).trim();
                    for (String proibido : proibidos) {
                        if (linha.startsWith(proibido)) {
                            encontradas.add("  %s:%d  %s".formatted(
                                    pacote.relativize(arquivo), i + 1, linha));
                        }
                    }
                }
            }
        }
        return encontradas;
    }
}
