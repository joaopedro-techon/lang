package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.itau.sg2.custodiaposvenda.infrastructure.logging.Logger;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.SdkBytes;
import software.amazon.awssdk.services.firehose.FirehoseAsyncClient;
import software.amazon.awssdk.services.firehose.model.PutRecordBatchRequest;
import software.amazon.awssdk.services.firehose.model.PutRecordBatchResponse;
import software.amazon.awssdk.services.firehose.model.Record;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;

@Component
public class FirehoseBatchClient {

    private static final int MAX_FIREHOSE_BATCH = 500;

    private final FirehoseAsyncClient firehoseAsyncClient;
    private final ObjectMapper objectMapper;

    public FirehoseBatchClient(FirehoseAsyncClient firehoseAsyncClient, ObjectMapper objectMapper) {
        this.firehoseAsyncClient = firehoseAsyncClient;
        this.objectMapper = objectMapper;
    }

    public <T> CompletableFuture<Void> enviar(String deliveryStreamName, List<T> eventos) {
        if (eventos == null || eventos.isEmpty()) {
            return CompletableFuture.completedFuture(null);
        }

        List<List<T>> batches = particionarEmBatches(eventos);
        List<CompletableFuture<Void>> futures = new ArrayList<>();

        for (List<T> batch : batches) {
            List<Record> records = batch.stream()
                    .map(evento -> toRecord(evento, deliveryStreamName))
                    .toList();

            PutRecordBatchRequest request = PutRecordBatchRequest.builder()
                    .deliveryStreamName(deliveryStreamName)
                    .records(records)
                    .build();

            CompletableFuture<Void> future = firehoseAsyncClient.putRecordBatch(request)
                    .thenAccept(response -> tratarResponse(response, batch.size(), deliveryStreamName));

            futures.add(future);
        }

        return CompletableFuture.allOf(futures.toArray(new CompletableFuture[0]));
    }

    private void tratarResponse(PutRecordBatchResponse response, int batchSize, String deliveryStreamName) {
        if (response.failedPutCount() > 0) {
            Logger.warn(String.format("Firehose retornou %d falhas no batch de %d records. stream=%s",
                    response.failedPutCount(), batchSize, deliveryStreamName));
        } else {
            Logger.info(String.format("Batch de %d records enviado com sucesso. stream=%s",
                    batchSize, deliveryStreamName));
        }
    }

    private <T> List<List<T>> particionarEmBatches(List<T> eventos) {
        List<List<T>> batches = new ArrayList<>();
        for (int i = 0; i < eventos.size(); i += MAX_FIREHOSE_BATCH) {
            batches.add(eventos.subList(i, Math.min(i + MAX_FIREHOSE_BATCH, eventos.size())));
        }
        return batches;
    }

    private <T> Record toRecord(T evento, String deliveryStreamName) {
        try {
            String json = objectMapper.writeValueAsString(evento) + "\n";
            return Record.builder()
                    .data(SdkBytes.fromByteArray(json.getBytes(StandardCharsets.UTF_8)))
                    .build();
        } catch (JsonProcessingException e) {
            throw new FirehosePublicacaoException("Erro ao serializar evento para JSON. stream=" + deliveryStreamName, e);
        }
    }
}
