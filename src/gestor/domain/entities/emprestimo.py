from django.db import models
from django.utils import timezone

from gestor.domain.entities.livro import Livro
from gestor.domain.entities.unidade import Unidade
from gestor.domain.entities.usuario import Usuario


class Emprestimo(models.Model):
    STATUS_ABERTO = "aberto"
    STATUS_DEVOLVIDO = "devolvido"
    STATUS_CHOICES = [
        (STATUS_ABERTO, "Aberto"),
        (STATUS_DEVOLVIDO, "Devolvido"),
    ]

    livro = models.ForeignKey(Livro, on_delete=models.CASCADE)
    unidade = models.ForeignKey(Unidade, on_delete=models.CASCADE, null=True, blank=True)
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    data_emprestimo = models.DateField(default=timezone.localdate)
    data_prevista_devolucao = models.DateField(null=True, blank=True)
    data_devolucao = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ABERTO)
    observacoes = models.TextField(null=True, blank=True)

    def __str__(self):
        unidade_nome = self.unidade.nome if self.unidade else "Sem unidade"
        return f"{self.livro.titulo} [{unidade_nome}] -> {self.usuario.nome} ({self.status})"

    class Meta:
        app_label = "gestor"
        ordering = ["-data_emprestimo", "-id"]
