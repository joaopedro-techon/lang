package com.itau.sg2.custodiaposvenda.application.ports.outbound;

import java.util.List;

public interface PublicadorAuditoriaPort {

    <T> void publicar(List<T> eventos);
}
