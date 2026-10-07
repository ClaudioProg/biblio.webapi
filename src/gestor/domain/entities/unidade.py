from django.db import models

class Unidade(models.Model):
    nome = models.CharField(max_length=255)
    endereco = models.TextField(null=True, blank=True)
    telefone = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    site = models.URLField(null=True, blank=True)
    ibge_bairro_codigo = models.CharField(max_length=10, null=True, blank=True, db_index=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    def __str__(self):
        return self.nome

    class Meta:
        app_label = 'gestor'
