from django.db import models


class Usuario(models.Model):
    nome = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    telefone = models.CharField(max_length=20, null=True, blank=True)
    documento = models.CharField(max_length=30, null=True, blank=True)
    ativo = models.BooleanField(default=True)
    observacoes = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.nome

    class Meta:
        app_label = "gestor"